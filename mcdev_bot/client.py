"""我的世界（中国版）开发者平台 —— 数据接口客户端。

▍接口来源
    通过分析 https://mcdev.webapp.163.com/ 前端打包资源得到，并已用真实账号逐项验证：
      · 接口基址   //mc-launcher.webapp.163.com/
      · 鉴权方式   Cookie（浏览器登录开发者平台后携带，withCredentials=true）
      · 数据响应   {"status": "ok", "data": {...}}

▍已验证的接口
    GET users/me                              当前登录开发者信息
    GET items/categories/{cate}/              名下作品列表（含 item_id，统计必需）
    GET data_analysis/overview/               账号级总览（昨日/14天/本月/上月）
    GET data_analysis/day_detail/             按天明细（钻石/销量/DAU…）
    GET data_analysis/month_detail/           按月明细（注意：口径与 overview 不一致，见下）

▍重要口径说明
    day_detail 的逐日数据与官方 overview 完全吻合（例：昨日 1880 钻石、近 14 天
    合计 15694 / 日均 1121），因此本模块**以 day_detail 为权威口径**。
    month_detail 的按月拆分与 overview 对不上（合计相同但月界不同），故不用于月报。

▍关键参数（踩坑记录）
    · start_date / end_date 必须是 YYYYMMDD（不带横线）
    · sort / order 中 order 必须大写 ASC / DESC（小写会返回 params error）
    · item_list_str 必填，且必须传具体作品 ID，否则返回空数据

⚠ 这些是开发者平台内部接口，官方未公开承诺稳定性；若平台改版，调整本文件即可。
"""
from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Union

import httpx

from .config import INCOME_CATE_MAP, Settings, settings as default_settings
from .models import DailyRow, ItemSummary, MonthlyRow, Settlement

DateLike = Union[str, date, datetime]


class McDevError(Exception):
    """接口调用异常。"""


class McDevAuthError(McDevError):
    """登录态失效（Cookie 过期或未配置）。"""


def _ymd(value: DateLike) -> str:
    """把日期统一成接口要求的 YYYYMMDD 格式。"""
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return text
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise McDevError(f"无法识别的日期：{value}")


class McDevClient:
    """开发者平台异步客户端。"""

    def __init__(self, config: Optional[Settings] = None) -> None:
        self.cfg = config or default_settings
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, tuple] = {}

    # ------------------------------------------------------------------
    # 基础设施
    # ------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {
            "Cookie": self.cfg.cookie,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://mcdev.webapp.163.com/",
            "Origin": "https://mcdev.webapp.163.com",
            "Accept": "application/json, text/plain, */*",
        }

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.cfg.base_url,
                headers=self._headers(),
                timeout=self.cfg.timeout,
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _cached(self, key: str) -> Optional[Any]:
        item = self._cache.get(key)
        if not item:
            return None
        value, expire = item
        if expire < time.time():
            self._cache.pop(key, None)
            return None
        return value

    def _store(self, key: str, value: Any) -> None:
        if self.cfg.cache_ttl > 0:
            self._cache[key] = (value, time.time() + self.cfg.cache_ttl)

    # ------------------------------------------------------------------
    # 请求与解包
    # ------------------------------------------------------------------
    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        if not self.cfg.cookie:
            raise McDevAuthError("未配置 MCDEV_COOKIE，无法访问开发者平台")
        client = await self._http()
        try:
            resp = await client.get(path, params=params or {})
        except httpx.HTTPError as exc:  # 网络层异常
            raise McDevError(f"请求 {path} 失败：{exc}") from exc
        return self._decode(resp, path)

    async def _post(self, path: str, json_body: Optional[dict] = None) -> dict:
        """POST 请求（用于秒杀名额查询等）。"""
        if not self.cfg.cookie:
            raise McDevAuthError("未配置 MCDEV_COOKIE，无法访问开发者平台")
        client = await self._http()
        try:
            resp = await client.post(path, json=json_body or {})
        except httpx.HTTPError as exc:
            raise McDevError(f"请求 {path} 失败：{exc}") from exc
        return self._decode(resp, path)

    def _decode(self, resp, path: str) -> dict:
        if resp.status_code in (401, 403):
            raise McDevAuthError("登录态已失效，请更新 MCDEV_COOKIE")
        if resp.status_code == 404:
            raise McDevError(f"接口 {path} 不存在（HTTP 404）")
        if resp.status_code != 200:
            raise McDevError(f"请求 {path} 返回 HTTP {resp.status_code}")

        try:
            payload = resp.json()
        except ValueError as exc:
            raise McDevError(f"接口 {path} 返回非 JSON（可能登录态失效）") from exc

        status = payload.get("status")
        code = payload.get("code")
        if status is not None and status not in ("ok", "success", 0):
            msg = payload.get("message") or payload.get("msg") or status
            raise McDevError(f"接口 {path} 返回异常：{msg}")
        if code is not None and code not in (0, 2, "0", "ok"):
            raise McDevError(f"接口 {path} 返回错误码：{code} {payload.get('message', '')}")

        data = payload.get("data")
        return data if isinstance(data, dict) else {"data": data}

    @staticmethod
    def _rows(data: dict) -> List[dict]:
        """从返回体中取出列表：兼容 data / items / item / list 等字段。"""
        if not isinstance(data, dict):
            return data if isinstance(data, list) else []
        for key in ("data", "items", "item", "incomes", "list", "records"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        return []

    # ------------------------------------------------------------------
    # 计算属性
    # ------------------------------------------------------------------
    @property
    def _cate(self) -> str:
        return INCOME_CATE_MAP.get(self.cfg.platform, "pe")

    # ------------------------------------------------------------------
    # 具体接口
    # ------------------------------------------------------------------
    async def get_user_info(self) -> dict:
        """users/me —— 用于校验登录态。"""
        return await self._get("users/me")

    async def check_login(self) -> bool:
        try:
            info = await self.get_user_info()
        except McDevError:
            return False
        return bool(info)

    async def get_items(self, category: Optional[str] = None) -> List[ItemSummary]:
        """items/categories/{cate}/ —— 名下作品列表（统计必须先拿到 item_id）。"""
        cate = category or self._cate
        key = f"items:{cate}"
        cached = self._cached(key)
        if cached is None:
            data = await self._get(f"items/categories/{cate}/")
            cached = [ItemSummary.parse(row) for row in self._rows(data)]
            self._store(key, cached)
        return cached

    async def get_item_ids(self, category: Optional[str] = None) -> List[str]:
        items = await self.get_items(category)
        return [item.item_id for item in items if item.item_id]

    async def get_overview(self) -> dict:
        """data_analysis/overview/ —— 账号级总览（官方口径）。"""
        return await self._get("data_analysis/overview/")

    async def get_day_detail(
        self,
        start_date: DateLike,
        end_date: DateLike,
        item_ids: Union[str, List[str]] = "",
        platform: Optional[str] = None,
        category: Optional[str] = None,
        sort: str = "dateid",
        order: str = "ASC",
        span: int = 200000,
        start: int = 0,
    ) -> List[DailyRow]:
        """data_analysis/day_detail/ —— 按天明细（权威口径）。"""
        if isinstance(item_ids, (list, tuple)):
            item_ids = ",".join(str(i) for i in item_ids if i)
        params = {
            "platform": platform or self.cfg.api_platform,
            "category": category or self.cfg.api_category,
            "start_date": _ymd(start_date),
            "end_date": _ymd(end_date),
            "item_list_str": item_ids,
            "sort": sort,
            "order": order.upper(),
            "start": start,
            "span": span,
        }
        key = f"day:{params}"
        cached = self._cached(key)
        if cached is None:
            data = await self._get("data_analysis/day_detail/", params)
            cached = [DailyRow.parse(row) for row in self._rows(data)]
            self._store(key, cached)
        return cached

    async def get_month_detail(
        self,
        start_date: DateLike,
        end_date: DateLike,
        item_ids: Union[str, List[str]] = "",
        platform: Optional[str] = None,
        category: Optional[str] = None,
        sort: str = "monthid",
        order: str = "DESC",
        span: int = 9999,
        start: int = 0,
    ) -> List[MonthlyRow]:
        """data_analysis/month_detail/ —— 按月明细。

        注意：该接口按月拆分与 overview 口径不一致，本项目的月报改用
        day_detail 聚合，此处保留以便后续对照或切换。
        """
        if isinstance(item_ids, (list, tuple)):
            item_ids = ",".join(str(i) for i in item_ids if i)
        params = {
            "platform": platform or self.cfg.api_platform,
            "category": category or self.cfg.api_category,
            "start_date": _ymd(start_date),
            "end_date": _ymd(end_date),
            "item_list_str": item_ids,
            "sort": sort,
            "order": order.upper(),
            "start": start,
            "span": span,
        }
        data = await self._get("data_analysis/month_detail/", params)
        return [MonthlyRow.parse(row) for row in self._rows(data)]

    async def get_settlements(self, platform: Optional[str] = None) -> List[Settlement]:
        """incomes/?platform=xxx —— 平台官方结算记录（按自然月）。

        返回的是平台结算页的真实数值：当月收益、累计可结算收益、累计消耗钻石、
        可分成流水、开发者分成、鼓励金额、罚款金额、畅玩计划收益、用量成本、税费等。
        """
        plat = platform or self.cfg.platform
        key = f"settlements:{plat}"
        cached = self._cached(key)
        if cached is None:
            data = await self._get("incomes/", {"platform": plat})
            cached = [Settlement.parse(row) for row in self._rows(data)]
            self._store(key, cached)
        return cached

    async def get_item_incomes(self, item_id: str) -> List[dict]:
        """items/categories/{cate}/{id}/incomes/ —— 单个作品收益明细。"""
        data = await self._get(f"items/categories/{self._cate}/{item_id}/incomes/")
        return self._rows(data)

    # ------------------------------------------------------------------
    # 玩家反馈 / 退款
    # ------------------------------------------------------------------
    async def get_feedback_list(self, span: int = 50) -> List[dict]:
        """items/feedback/pe/ —— 玩家反馈列表（含回复状态、模组、内容）。"""
        key = f"feedback:{span}"
        cached = self._cached(key)
        if cached is None:
            data = await self._get("items/feedback/pe/", {"start": 0, "span": span})
            cached = self._rows(data)
            self._store(key, cached)
        return cached

    async def get_refund_reasons(self, start: str = "", end: str = "", span: int = 200) -> List[dict]:
        """data_analysis/refund_reason/ —— 退款账单（含模组、退款日期、退款原因）。"""
        params = {"start": 0, "span": span}
        if start:
            params["start_date"] = start
        if end:
            params["end_date"] = end
        key = f"refund:{start}:{end}:{span}"
        cached = self._cached(key)
        if cached is None:
            data = await self._get("data_analysis/refund_reason/", params)
            cached = self._rows(data)
            self._store(key, cached)
        return cached

    # ------------------------------------------------------------------
    # 活动（征集 / 折扣特卖 / 优惠券 / 官方联动）
    # ------------------------------------------------------------------
    async def get_review_activities(self, span: int = 50) -> List[dict]:
        """activities/pe-review-activities/ —— 模组征集（评审）活动列表。"""
        data = await self._get("activities/pe-review-activities/", {"start": 0, "span": span})
        return self._rows(data)

    async def get_discount_activity(self) -> dict:
        """activities/discount_activities/current/ —— 当前折扣特卖活动。"""
        data = await self._get("activities/discount_activities/current/")
        return data.get("data", data) if isinstance(data, dict) else {}

    async def get_coupon_activity(self) -> List[dict]:
        """activities/coupon_activities/current/ —— 当前优惠券活动。"""
        data = await self._get("activities/coupon_activities/current/")
        rows = data.get("coupon_activities") if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else []

    async def get_joint_activity(self) -> List[dict]:
        """items/categories/pe/get_joint_activity —— 官方联动活动。"""
        data = await self._get("items/categories/pe/get_joint_activity")
        return self._rows(data)

    # ------------------------------------------------------------------
    # 周末秒杀
    # ------------------------------------------------------------------
    async def get_flashsale_quota(self, dates: Sequence[str]) -> dict:
        """items/apply_flashsale_num —— 查询各候选日期的秒杀名额占用。

        返回 ``{"daily_quota": int, "res_info": {date: used}}``。
        """
        if not dates:
            return {"daily_quota": 0, "res_info": {}}
        data = await self._post("items/apply_flashsale_num", {"date": ",".join(dates)})
        return data if isinstance(data, dict) else {}

    async def get_flashsale_history(self) -> List[dict]:
        """items/apply_flashsale_history —— 秒杀申请历史。"""
        data = await self._post("items/apply_flashsale_history", {})
        rows = data.get("res_info") if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else []

    async def apply_flashsale(self, item_id: str, date: str, num: int = 1000) -> dict:
        """items/apply_flashsale —— 提交周末秒杀申请（会改变平台状态）。"""
        return await self._post(
            "items/apply_flashsale",
            {"item_id": item_id, "date": date, "flashsale_num": int(num)},
        )


__all__ = ["McDevClient", "McDevError", "McDevAuthError"]
