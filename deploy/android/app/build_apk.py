"""不依赖 Gradle 的 APK 构建脚本（aapt2 + javac + d8 + zipalign + apksigner）。

用法：
    python deploy/android/app/build_apk.py

需要的环境变量（或用默认值）：
    ANDROID_SDK   默认 C:\\Android\\sdk
    JAVA_HOME     可选；不设则用 PATH 里的 java/javac

产物：``dist/mcdev-console.apk``
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parents[2]
SDK = Path(os.getenv("ANDROID_SDK", r"C:\Android\sdk"))
BT = SDK / "build-tools" / "34.0.0"
PLATFORM_JAR = SDK / "platforms" / "android-35" / "android.jar"

# d8（R8 8.2）在 JDK 21+ 上会崩，必须用 JDK 17 构建
JDK = Path(os.getenv("MCDev_JDK17", os.getenv("JDK17_HOME", r"C:\Android\jdk17")))
JAVAC = JDK / "bin" / "javac.exe"
KEYTOOL = JDK / "bin" / "keytool.exe"

BUILD = APP / "build"
DIST = ROOT / "dist"

KEYSTORE = APP / "release.keystore"
KS_PASS = "mcdev2026"
KS_ALIAS = "mcdev"
APK_NAME = "mcdev-console.apk"


def _env() -> dict:
    """让 d8.bat / apksigner.bat 使用 JDK 17。"""
    env = os.environ.copy()
    if (JDK / "bin").exists():
        env["JAVA_HOME"] = str(JDK)
        env["PATH"] = str(JDK / "bin") + os.pathsep + env.get("PATH", "")
    return env


def run(cmd, cwd=None, allow_fail=False):
    print("  $", " ".join(str(c) for c in cmd))
    proc = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_env(),
    )
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        if not allow_fail:
            raise SystemExit(f"命令失败（{proc.returncode}）：{cmd[0]}")
    return proc


def main() -> int:
    for p in (BT, PLATFORM_JAR):
        if not p.exists():
            print(f"!! 缺少 {p}", file=sys.stderr)
            print("   请先安装 Android build-tools 34.0.0 与 platform android-35", file=sys.stderr)
            return 1
    if not JAVAC.exists():
        print(f"!! 缺少 JDK 17：{JAVAC}", file=sys.stderr)
        print("   可用华为镜像下载：", file=sys.stderr)
        print("   https://mirrors.huaweicloud.com/openjdk/17.0.2/"
              "openjdk-17.0.2_windows-x64_bin.zip", file=sys.stderr)
        print("   解压到 C:\\Android\\jdk17 即可", file=sys.stderr)
        return 1

    if BUILD.exists():
        shutil.rmtree(BUILD)
    (BUILD / "gen").mkdir(parents=True)
    (BUILD / "classes").mkdir()
    (BUILD / "dex").mkdir()
    DIST.mkdir(parents=True, exist_ok=True)

    # 1) 编译资源
    print("[1/6] aapt2 compile")
    run([BT / "aapt2.exe", "compile", "--dir", APP / "res", "-o", BUILD / "res.zip"])

    # 2) 链接资源 + 生成 R.java + 打包 assets
    print("[2/6] aapt2 link")
    run([
        BT / "aapt2.exe", "link",
        "-o", BUILD / "base.apk",
        "-I", PLATFORM_JAR,
        "--manifest", APP / "AndroidManifest.xml",
        "-R", BUILD / "res.zip",
        "-A", APP / "assets",
        "--java", BUILD / "gen",
        "--min-sdk-version", "24",
        "--target-sdk-version", "34",
        "--auto-add-overlay",
    ])

    # 3) 编译 Java
    print("[3/6] javac")
    sources = [str(p) for p in (BUILD / "gen").rglob("*.java")]
    sources += [str(p) for p in (APP / "java").rglob("*.java")]
    run([
        JAVAC, "--release", "11",
        "-encoding", "UTF-8",
        "-classpath", PLATFORM_JAR,
        "-d", BUILD / "classes",
        *sources,
    ])

    # 4) d8 生成 dex
    print("[4/6] d8")
    classes = [str(p) for p in (BUILD / "classes").rglob("*.class")]
    run([
        BT / "d8.bat",
        "--release",
        "--min-api", "24",
        "--lib", PLATFORM_JAR,
        "--output", BUILD / "dex",
        *classes,
    ])

    # 5) 把 classes.dex 放进 apk
    print("[5/6] 打包 dex")
    with zipfile.ZipFile(BUILD / "base.apk", "a", zipfile.ZIP_DEFLATED) as zf:
        for dex in sorted((BUILD / "dex").glob("classes*.dex")):
            zf.write(dex, dex.name)

    run([BT / "zipalign.exe", "-f", "4", BUILD / "base.apk", BUILD / "aligned.apk"])

    # 6) 签名
    print("[6/6] 签名")
    if not KEYSTORE.exists():
        run([
            KEYTOOL, "-genkeypair", "-v",
            "-keystore", KEYSTORE,
            "-alias", KS_ALIAS,
            "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
            "-storepass", KS_PASS,
            "-keypass", KS_PASS,
            "-dname", "CN=MCDev Console, OU=Dev, O=MCDev, L=NA, S=NA, C=CN",
        ])

    out_apk = DIST / APK_NAME
    if out_apk.exists():
        out_apk.unlink()
    run([
        BT / "apksigner.bat", "sign",
        "--ks", KEYSTORE,
        "--ks-pass", f"pass:{KS_PASS}",
        "--key-pass", f"pass:{KS_PASS}",
        "--ks-key-alias", KS_ALIAS,
        "--out", out_apk,
        BUILD / "aligned.apk",
    ])
    run([BT / "apksigner.bat", "verify", "--print-certs", out_apk], allow_fail=True)

    size = out_apk.stat().st_size
    print()
    print("=" * 56)
    print(f"构建完成：{out_apk}")
    print(f"大小：{size / 1024 / 1024:.2f} MB")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
