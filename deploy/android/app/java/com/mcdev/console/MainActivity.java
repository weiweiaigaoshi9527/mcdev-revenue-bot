package com.mcdev.console;

import android.annotation.SuppressLint;
import android.content.ComponentName;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import android.app.Activity;

/**
 * 控制台 App：用 WebView 加载 Termux 里运行的本地面板。
 *
 * 面板地址固定为 http://127.0.0.1:8770/（只监听回环，不对外暴露）。
 * 连不上时展示离线页，并提供「一键启动机器人」按钮，
 * 通过 Termux 的 RUN_COMMAND 接口执行 watchdog.sh。
 */
public class MainActivity extends Activity {

    private static final String CONSOLE_URL = "http://127.0.0.1:8770/";
    private static final String OFFLINE_URL = "file:///android_asset/offline.html";

    private WebView web;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        web.addJavascriptInterface(new Bridge(), "Android");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                return false;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                // 只有主文档失败时才切到离线页，避免图片等子资源失败误触发
                if (req != null && req.isForMainFrame()) {
                    view.loadUrl(OFFLINE_URL);
                }
            }

            @SuppressWarnings("deprecation")
            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
                    view.loadUrl(OFFLINE_URL);
                }
            }
        });

        web.loadUrl(CONSOLE_URL);
    }

    /** 给网页调用的原生桥 */
    public class Bridge {
        @JavascriptInterface
        public void startBot() {
            runTermuxCommand("cd ~/qqbot && ./deploy/android/watchdog.sh start");
        }

        @JavascriptInterface
        public void stopBot() {
            runTermuxCommand("cd ~/qqbot && ./deploy/android/watchdog.sh stop");
        }

        @JavascriptInterface
        public void reload() {
            runOnUiThread(() -> web.loadUrl(CONSOLE_URL));
        }

        @JavascriptInterface
        public void toast(final String msg) {
            runOnUiThread(() ->
                    Toast.makeText(MainActivity.this, msg, Toast.LENGTH_SHORT).show());
        }
    }

    /** 通过 Termux:RunCommandService 执行脚本（需要 Termux 打开 allow-external-apps） */
    private void runTermuxCommand(String command) {
        try {
            Intent intent = new Intent();
            intent.setComponent(new ComponentName(
                    "com.termux", "com.termux.app.RunCommandService"));
            intent.setAction("com.termux.RUN_COMMAND");
            intent.putExtra("com.termux.RUN_COMMAND_PATH",
                    "/data/data/com.termux/files/usr/bin/bash");
            intent.putExtra("com.termux.RUN_COMMAND_ARGUMENTS",
                    new String[]{"-c", command});
            intent.putExtra("com.termux.RUN_COMMAND_WORKDIR",
                    "/data/data/com.termux/files/home");
            intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(intent);
            } else {
                startService(intent);
            }
            Toast.makeText(this, "已请求 Termux 执行，请稍候刷新", Toast.LENGTH_LONG).show();
        } catch (SecurityException e) {
            Toast.makeText(this,
                    "缺少 Termux 执行权限：请在系统设置里给本应用授予「Termux: RUN_COMMAND」权限",
                    Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            Toast.makeText(this,
                    "无法调用 Termux，请确认已安装 Termux 并开启 allow-external-apps",
                    Toast.LENGTH_LONG).show();
        }
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && web != null) {
            if (web.getUrl() != null && web.getUrl().startsWith("file:")) {
                web.loadUrl(CONSOLE_URL);
                return true;
            }
            if (web.canGoBack()) {
                web.goBack();
                return true;
            }
        }
        return super.onKeyDown(keyCode, event);
    }
}
