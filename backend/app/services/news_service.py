import feedparser
import urllib.parse
from datetime import datetime, timedelta
import logging
import re
import html
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.cache import cache_manager

logger = logging.getLogger(__name__)

class NewsService:
    def __init__(self):
        # Using centralized Redis cache_manager instead of local memory dicts
        pass

    def clean_company_name(self, name: str, symbol: str) -> str:
        """
        Cleans corporate suffixes from company names to construct broader,
        more relevant search queries.
        """
        if not name or name.upper() == symbol.upper():
            return symbol.split(".")[0]

        # Convert HTML entities if present
        clean = html.unescape(name)
        
        # Remove standard legal/corporate designations (case-insensitive)
        suffixes = [
            r"\bLTD\b\.?", r"\bLIMITED\b", r"\bCORP\b\.?", r"\bCORPORATION\b",
            r"\bINC\b\.?", r"\bINCORPORATED\b", r"\bPLC\b\.?", r"\bCO\b\.?",
            r"\bCOMPANY\b", r"\bSA\b", r"\bAG\b", r"\bSE\b", r"\bIND\b\.?",
            r"\bINDUSTRIES\b"
        ]
        
        for suffix in suffixes:
            clean = re.sub(suffix, "", clean, flags=re.IGNORECASE)

        # Remove ticker/suffix if it slipped into name
        clean = re.sub(r"\b" + re.escape(symbol.split(".")[0]) + r"\b", "", clean, flags=re.IGNORECASE)
        
        # Strip trailing special symbols and excess spaces
        clean = re.sub(r"[,.\-&()\[\]]+", " ", clean)
        clean = " ".join(clean.split())
        
        # If cleaning wiped it out or made it too short, fallback
        if len(clean) < 3:
            return symbol.split(".")[0]
            
        return clean

    def _parse_pubdate(self, entry: Any) -> datetime:
        """
        Parse RSS publication date into datetime object.
        """
        try:
            if "published_parsed" in entry and entry.published_parsed:
                return datetime(*entry.published_parsed[:6])
        except Exception:
            pass
        return datetime.utcnow()
        
    def _is_duplicate(self, title: str, seen_titles: set) -> bool:
        """Helper to check if a title overlaps significantly with already seen titles."""
        norm_title = re.sub(r"\W+", " ", title.lower()).strip()
        words = set(norm_title.split())
        
        for seen in seen_titles:
            seen_words = set(seen.split())
            if not words or not seen_words:
                continue
            overlap = len(words.intersection(seen_words)) / max(len(words), len(seen_words))
            if overlap > 0.7:  # 70% threshold overlap
                return True
                
        seen_titles.add(norm_title)
        return False

    def fetch_news_for_symbol(self, symbol: str, company_name: str) -> List[Dict[str, Any]]:
        """
        Fetch and parse real-time headlines for a symbol from Google News RSS.
        Implements title suffix trimming, deduplication, and thread-safe caching (1-hour TTL).
        """
        symbol = symbol.upper().strip()

        cache_key = f"news_service:symbol:{symbol}"
        cached = cache_manager.get(cache_key)
        if cached is not None:
            return cached

        cleaned_name = self.clean_company_name(company_name, symbol)
        
        # Generate search query search string
        # Target exact name query OR the raw symbol
        query = f'"{cleaned_name}" OR "{symbol.split(".")[0]}"'
        
        # Geolocation configuration: Indian endpoints vs Global endpoints
        is_indian = symbol.endswith(".NS") or symbol.endswith(".BO")
        if is_indian:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
        else:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"

        items = []
        try:
            feed = feedparser.parse(url)
            entries = feed.entries or []

            seen_titles = set()
            for entry in entries:
                title = entry.get("title", "")
                if not title:
                    continue

                # 1. Clean Publisher Suffixes (e.g. "- Economic Times")
                # Split from right to trim standard source suffix
                cleaned_title = title
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    cleaned_title = parts[0]
                elif " | " in title:
                    parts = title.rsplit(" | ", 1)
                    cleaned_title = parts[0]

                if self._is_duplicate(cleaned_title, seen_titles):
                    continue

                # Resolve publisher name
                source = "Unknown Source"
                if "source" in entry and entry.source:
                    source = entry.source.get("title", "Unknown Source")
                elif " - " in title:
                    source = title.rsplit(" - ", 1)[-1]
                elif " | " in title:
                    source = title.rsplit(" | ", 1)[-1]

                pub_datetime = self._parse_pubdate(entry)

                items.append({
                    "title": cleaned_title,
                    "link": entry.get("link", ""),
                    "source": source,
                    "published_at": pub_datetime.isoformat() + "Z"
                })

                # Limit to top 5 highly relevant articles per ticker to avoid noise
                if len(items) >= 5:
                    break

        except Exception as e:
            logger.error(f"Error fetching RSS news for {symbol}: {e}", exc_info=True)

        # Cache results for 1 hour (3600 seconds)
        cache_manager.set(cache_key, items, ttl=3600)
        return items

    def fetch_news_bulk(self, symbols_map: Dict[str, str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch news for a map of symbol -> company_name.
        Executes network-bound RSS fetches concurrently using a thread pool.
        """
        results = {}
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_symbol = {
                executor.submit(self.fetch_news_for_symbol, sym, name): sym
                for sym, name in symbols_map.items()
            }
            
            for future in as_completed(future_to_symbol):
                sym = future_to_symbol[future]
                try:
                    results[sym] = future.result()
                except Exception as e:
                    logger.error(f"Error fetching bulk news for {sym}: {e}", exc_info=True)
                    results[sym] = []
                    
        return results

    def search_news(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Perform a query-aware financial and business news search on Google News RSS.
        """
        query = query.strip()
        if not query:
            return []
            
        cache_key = f"news_service:search:{query}"
        cached = cache_manager.get(cache_key)
        if cached is not None:
            return cached

        is_indian = any(k in query.lower() for k in ["india", "nifty", "nse", "bse", "rbi", "rupee", "₹", "inr"])
        if is_indian:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
        else:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"

        items = []
        try:
            feed = feedparser.parse(url)
            entries = feed.entries or []

            seen_titles = set()
            for entry in entries:
                title = entry.get("title", "")
                if not title:
                    continue

                cleaned_title = title
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    cleaned_title = parts[0]
                elif " | " in title:
                    parts = title.rsplit(" | ", 1)
                    cleaned_title = parts[0]

                if self._is_duplicate(cleaned_title, seen_titles):
                    continue

                source = "Unknown Source"
                if "source" in entry and entry.source:
                    source = entry.source.get("title", "Unknown Source")
                elif " - " in title:
                    source = title.rsplit(" - ", 1)[-1]
                elif " | " in title:
                    source = title.rsplit(" | ", 1)[-1]

                pub_datetime = self._parse_pubdate(entry)

                items.append({
                    "title": cleaned_title,
                    "link": entry.get("link", ""),
                    "source": source,
                    "published_at": pub_datetime.isoformat() + "Z"
                })

                if len(items) >= max_results:
                    break

        except Exception as e:
            logger.error(f"Error searching RSS news for '{query}': {e}", exc_info=True)

        # Cache search results for 10 minutes
        cache_manager.set(cache_key, items, ttl=600)
        return items

    def get_why_matters_label(
        self, 
        symbol: str, 
        sector: str, 
        cap_bucket: str, 
        holding_qty: float, 
        return_since_added: float = None
    ) -> str:
        """
        Generates context-aware explanations of why a news asset matters to the user's portfolio.
        """
        if holding_qty > 0:
            return f"Active holding ({cap_bucket.capitalize()} Cap) in the {sector} sector. Keep track of earnings, growth trends, and contract cycles."
        elif return_since_added is not None:
            return f"Watched candidate in the {sector} sector with returns since added of {return_since_added}%."
        else:
            return f"Watched candidate in the {sector} sector. Monitored for potential diversification benefits."

news_service = NewsService()
