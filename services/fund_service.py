from __future__ import annotations

from dataclasses import dataclass

import akshare as ak
import pandas as pd


class FundDataError(Exception):
    """基金数据查询失败异常。"""


@dataclass
class FundHistory:
    code: str
    name: str
    dataframe: pd.DataFrame


class FundService:
    """负责从 AkShare 拉取并标准化基金净值数据。"""

    UNIT_NAV_INDICATOR = "单位净值走势"
    ACC_NAV_INDICATOR = "累计净值走势"

    def get_fund_history(self, fund_code: str) -> FundHistory:
        code = self._normalize_code(fund_code)
        try:
            unit_df = ak.fund_open_fund_info_em(
                symbol=code,
                indicator=self.UNIT_NAV_INDICATOR,
            )
            acc_df = ak.fund_open_fund_info_em(
                symbol=code,
                indicator=self.ACC_NAV_INDICATOR,
            )
        except Exception as exc:  # noqa: BLE001
            raise FundDataError(f"查询基金 {code} 失败，请检查网络或基金代码。") from exc

        normalized = self._build_history_dataframe(unit_df, acc_df)
        if normalized.empty:
            raise FundDataError(f"基金 {code} 没有可用净值数据。")

        fund_name = self._extract_fund_name(unit_df, acc_df)
        if fund_name == "未知基金":
            fund_name = self._lookup_fund_name_by_code(code)
        return FundHistory(code=code, name=fund_name, dataframe=normalized)

    @staticmethod
    def _normalize_code(fund_code: str) -> str:
        code = fund_code.strip()
        if not code.isdigit() or len(code) != 6:
            raise FundDataError("基金代码格式错误，应为 6 位数字，例如 161725。")
        return code

    @staticmethod
    def _extract_fund_name(unit_df: pd.DataFrame, acc_df: pd.DataFrame) -> str:
        for df in (unit_df, acc_df):
            if "基金简称" in df.columns and not df["基金简称"].dropna().empty:
                return str(df["基金简称"].dropna().iloc[0])
        return "未知基金"

    @staticmethod
    def _lookup_fund_name_by_code(code: str) -> str:
        """从基金列表中按代码兜底查询基金简称。"""
        try:
            fund_name_df = ak.fund_name_em()
        except Exception:  # noqa: BLE001
            return "未知基金"

        if fund_name_df.empty:
            return "未知基金"

        code_col = next((col for col in fund_name_df.columns if "代码" in str(col)), None)
        name_col = next((col for col in fund_name_df.columns if "简称" in str(col)), None)
        if code_col is None or name_col is None:
            return "未知基金"

        code_series = fund_name_df[code_col].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
        matched = fund_name_df.loc[code_series == code, name_col]
        if matched.empty:
            return "未知基金"
        return str(matched.iloc[0])

    @staticmethod
    def _build_history_dataframe(unit_df: pd.DataFrame, acc_df: pd.DataFrame) -> pd.DataFrame:
        merged = pd.DataFrame()

        if not unit_df.empty and {"净值日期", "单位净值"}.issubset(unit_df.columns):
            unit = unit_df[["净值日期", "单位净值"]].copy()
            unit["净值日期"] = pd.to_datetime(unit["净值日期"], errors="coerce")
            unit["单位净值"] = pd.to_numeric(unit["单位净值"], errors="coerce")
            merged = unit.rename(columns={"单位净值": "unit_nav"})

        if not acc_df.empty and {"净值日期", "累计净值"}.issubset(acc_df.columns):
            acc = acc_df[["净值日期", "累计净值"]].copy()
            acc["净值日期"] = pd.to_datetime(acc["净值日期"], errors="coerce")
            acc["累计净值"] = pd.to_numeric(acc["累计净值"], errors="coerce")
            acc = acc.rename(columns={"累计净值": "acc_nav"})
            merged = acc if merged.empty else pd.merge(merged, acc, on="净值日期", how="outer")

        if merged.empty:
            return merged

        merged = merged.dropna(subset=["净值日期"]).sort_values("净值日期")
        merged = merged.drop_duplicates(subset=["净值日期"], keep="last")
        merged = merged.reset_index(drop=True)
        return merged
