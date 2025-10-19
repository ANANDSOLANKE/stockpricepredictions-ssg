# scripts/logo_map.py
import csv
import os
from typing import Dict, Tuple, Optional

Key = Tuple[str, str, str]  # (country_slug.lower(), exchange.upper(), symbol.upper())

class LogoMap:
    """
    Simple loader for logos.csv that resolves a logo URL for (country, exchange, symbol).
    Assumes repo structure: logos/<country_slug>/<EXCHANGE>/<logo_file>
    """
    def __init__(self, repo_root: str = ".",
                 mapping_relpaths=("logos/_map/logos.csv", "logos/logos.csv")) -> None:
        self.repo_root = os.path.abspath(repo_root)
        self.mapping_path = None
        for rel in mapping_relpaths:
            p = os.path.join(self.repo_root, rel)
            if os.path.isfile(p):
                self.mapping_path = p
                break
        self._map: Dict[Key, str] = {}
        self._exdir_cache: Dict[Tuple[str, str], Optional[str]] = {}  # (country_slug, exch_raw) -> EXCH_DIR (case)
        if self.mapping_path:
            self._load()

    def _load(self) -> None:
        with open(self.mapping_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                country = (row.get("country_slug") or "").strip().lower()
                exch_raw = (row.get("exchange") or "").strip()
                symbol = (row.get("symbol") or "").strip().upper()
                logo_file = (row.get("logo_file") or "").strip()
                if not (country and exch_raw and symbol and logo_file):
                    continue

                exch_dir = self._resolve_exchange_dir(country, exch_raw)
                if not exch_dir:
                    # exchange folder not present — skip
                    continue

                rel_logo = f"/logos/{country}/{exch_dir}/{logo_file}"
                key: Key = (country, exch_dir.upper(), symbol)
                self._map[key] = rel_logo

    def _resolve_exchange_dir(self, country: str, exch_raw: str) -> Optional[str]:
        """
        Make exchange directory case match the folder name that exists on disk.
        Example: input 'nse' or 'NSE' -> finds 'NSE' under logos/india/
        """
        cache_key = (country, exch_raw)
        if cache_key in self._exdir_cache:
            return self._exdir_cache[cache_key]

        country_dir = os.path.join(self.repo_root, "logos", country)
        if not os.path.isdir(country_dir):
            self._exdir_cache[cache_key] = None
            return None

        want = exch_raw.strip().lower()
        for d in os.listdir(country_dir):
            full = os.path.join(country_dir, d)
            if os.path.isdir(full) and d.lower() == want:
                self._exdir_cache[cache_key] = d  # keep original case as in repo
                return d

        self._exdir_cache[cache_key] = None
        return None

    def get_url(self, country_slug: str, exchange: str, symbol: str) -> str:
        """
        Return the logo URL (like '/logos/india/NSE/3m--600.png') or '' if not found.
        """
        if not self._map:
            return ""
        key: Key = (country_slug.strip().lower(), exchange.strip().upper(), symbol.strip().upper())
        return self._map.get(key, "")
