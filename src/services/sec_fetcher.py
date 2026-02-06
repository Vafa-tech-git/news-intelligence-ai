"""
SEC Insider Trading Fetcher
Fetch and analyze SEC Form 4 filings for insider trading activity.

Form 4 is filed when company insiders (executives, directors, major shareholders)
buy or sell company stock. This is valuable alternative data because:
- Insiders have the best information about their company
- Clustered insider buying often precedes stock price increases
- Large insider selling may signal concerns about future performance
"""

import requests
from xml.etree import ElementTree
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from statistics import mean
import json
import re

import database


class SECInsiderFetcher:
    """Fetch and analyze SEC Form 4 insider trading filings."""

    BASE_URL = "https://www.sec.gov"
    SEARCH_URL = f"{BASE_URL}/cgi-bin/browse-edgar"

    # SEC requires a user agent with contact info
    HEADERS = {
        'User-Agent': 'NewsIntelligenceAI/1.0 (contact@example.com)',
        'Accept': 'application/json, application/xml, text/html',
        'Accept-Encoding': 'gzip, deflate'
    }

    # Common insider titles
    EXECUTIVE_TITLES = ['CEO', 'CFO', 'COO', 'CTO', 'President', 'Chairman', 'Director']

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def search_company_filings(self, ticker: str, filing_type: str = '4', count: int = 40) -> List[Dict]:
        """
        Search for recent SEC filings by ticker.

        Args:
            ticker: Stock ticker symbol
            filing_type: Filing type ('4' for Form 4)
            count: Number of filings to retrieve

        Returns:
            List of filing metadata
        """
        params = {
            'action': 'getcompany',
            'CIK': ticker,
            'type': filing_type,
            'dateb': '',
            'owner': 'include',
            'count': count,
            'output': 'atom'
        }

        try:
            response = self.session.get(self.SEARCH_URL, params=params, timeout=30)
            response.raise_for_status()

            # Parse Atom feed
            filings = self._parse_atom_feed(response.text)
            return filings

        except requests.RequestException as e:
            print(f"[SEC] Error fetching filings for {ticker}: {e}")
            return []

    def _parse_atom_feed(self, xml_content: str) -> List[Dict]:
        """Parse SEC Atom feed XML into filing list."""
        filings = []

        try:
            root = ElementTree.fromstring(xml_content)

            # Namespace handling for Atom
            ns = {'atom': 'http://www.w3.org/2005/Atom'}

            for entry in root.findall('.//atom:entry', ns):
                title = entry.find('atom:title', ns)
                updated = entry.find('atom:updated', ns)
                link = entry.find('atom:link', ns)
                summary = entry.find('atom:summary', ns)

                if title is not None:
                    filing = {
                        'title': title.text,
                        'filed_date': updated.text[:10] if updated is not None else None,
                        'link': link.get('href') if link is not None else None,
                        'summary': summary.text if summary is not None else None
                    }

                    # Parse title for additional info
                    # Format: "4 - Insider Name (Officer Title)"
                    title_text = title.text or ''
                    if ' - ' in title_text:
                        parts = title_text.split(' - ', 1)
                        if len(parts) > 1:
                            name_part = parts[1]
                            filing['insider_name'] = name_part.split('(')[0].strip()

                            # Extract title if present
                            title_match = re.search(r'\(([^)]+)\)', name_part)
                            if title_match:
                                filing['insider_title'] = title_match.group(1)

                    filings.append(filing)

        except ElementTree.ParseError as e:
            print(f"[SEC] Error parsing Atom feed: {e}")

        return filings

    def get_form4_details(self, filing_url: str) -> Optional[Dict]:
        """
        Get detailed Form 4 transaction data.

        Args:
            filing_url: URL to the Form 4 filing

        Returns:
            Dict with transaction details or None
        """
        try:
            # Get the index page
            response = self.session.get(filing_url, timeout=30)
            response.raise_for_status()

            # Find the XML link in the filing
            # Form 4 filings have an associated XML file
            xml_link = self._find_xml_link(response.text, filing_url)

            if xml_link:
                xml_response = self.session.get(xml_link, timeout=30)
                xml_response.raise_for_status()
                return self._parse_form4_xml(xml_response.text)

            return None

        except requests.RequestException as e:
            print(f"[SEC] Error fetching Form 4 details: {e}")
            return None

    def _find_xml_link(self, html_content: str, base_url: str) -> Optional[str]:
        """Find the XML file link in the filing index page."""
        # Look for XML file pattern
        xml_pattern = re.search(r'href="([^"]*\.xml)"', html_content)
        if xml_pattern:
            xml_path = xml_pattern.group(1)
            if xml_path.startswith('/'):
                return f"{self.BASE_URL}{xml_path}"
            else:
                # Construct full URL from base
                base_parts = base_url.rsplit('/', 1)
                return f"{base_parts[0]}/{xml_path}"
        return None

    def _parse_form4_xml(self, xml_content: str) -> Dict:
        """Parse Form 4 XML for transaction details."""
        result = {
            'transactions': [],
            'total_bought': 0,
            'total_sold': 0,
            'total_value': 0
        }

        try:
            root = ElementTree.fromstring(xml_content)

            # Get issuer info
            issuer = root.find('.//issuer')
            if issuer is not None:
                result['issuer_ticker'] = issuer.findtext('issuerTradingSymbol', '')
                result['issuer_name'] = issuer.findtext('issuerName', '')
                result['issuer_cik'] = issuer.findtext('issuerCik', '')

            # Get reporting owner
            owner = root.find('.//reportingOwner')
            if owner is not None:
                owner_id = owner.find('reportingOwnerId')
                if owner_id is not None:
                    result['owner_name'] = owner_id.findtext('rptOwnerName', '')
                    result['owner_cik'] = owner_id.findtext('rptOwnerCik', '')

                # Get relationship
                relationship = owner.find('reportingOwnerRelationship')
                if relationship is not None:
                    result['is_director'] = relationship.findtext('isDirector', '0') == '1'
                    result['is_officer'] = relationship.findtext('isOfficer', '0') == '1'
                    result['is_ten_percent_owner'] = relationship.findtext('isTenPercentOwner', '0') == '1'
                    result['officer_title'] = relationship.findtext('officerTitle', '')

            # Get non-derivative transactions (common stock)
            for tx in root.findall('.//nonDerivativeTransaction'):
                transaction = self._parse_transaction(tx)
                if transaction:
                    result['transactions'].append(transaction)

                    # Aggregate
                    if transaction['acquired_disposed'] == 'A':
                        result['total_bought'] += transaction.get('shares', 0)
                    else:
                        result['total_sold'] += transaction.get('shares', 0)

                    result['total_value'] += transaction.get('value', 0)

        except ElementTree.ParseError as e:
            print(f"[SEC] Error parsing Form 4 XML: {e}")

        return result

    def _parse_transaction(self, tx_element) -> Optional[Dict]:
        """Parse a single transaction element."""
        try:
            security = tx_element.find('securityTitle')
            amounts = tx_element.find('transactionAmounts')
            coding = tx_element.find('transactionCoding')
            date_elem = tx_element.find('transactionDate')

            if amounts is None:
                return None

            transaction = {
                'security_title': security.findtext('value', '') if security is not None else '',
                'date': date_elem.findtext('value', '') if date_elem is not None else ''
            }

            # Transaction coding
            if coding is not None:
                transaction['transaction_code'] = coding.findtext('transactionCode', '')
                # P = Purchase, S = Sale, A = Award, M = Exercise

            # Shares
            shares_elem = amounts.find('transactionShares')
            if shares_elem is not None:
                shares_str = shares_elem.findtext('value', '0')
                transaction['shares'] = int(float(shares_str)) if shares_str else 0

            # Price
            price_elem = amounts.find('transactionPricePerShare')
            if price_elem is not None:
                price_str = price_elem.findtext('value', '0')
                transaction['price'] = float(price_str) if price_str else 0

            # Acquired or Disposed
            ad_elem = amounts.find('transactionAcquiredDisposedCode')
            if ad_elem is not None:
                transaction['acquired_disposed'] = ad_elem.findtext('value', '')

            # Calculate value
            transaction['value'] = transaction.get('shares', 0) * transaction.get('price', 0)

            return transaction

        except Exception as e:
            print(f"[SEC] Error parsing transaction: {e}")
            return None

    def get_insider_sentiment(self, ticker: str, days: int = 90) -> Dict:
        """
        Calculate insider sentiment for a ticker.

        Args:
            ticker: Stock ticker
            days: Number of days to analyze

        Returns:
            Dict with insider sentiment metrics
        """
        filings = self.search_company_filings(ticker, count=50)

        if not filings:
            return {
                'ticker': ticker,
                'insider_sentiment': 0,
                'data_available': False,
                'reason': 'No filings found'
            }

        # Filter by date
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_filings = []

        for f in filings:
            if f.get('filed_date'):
                try:
                    filing_date = datetime.strptime(f['filed_date'], '%Y-%m-%d')
                    if filing_date >= cutoff_date:
                        recent_filings.append(f)
                except ValueError:
                    continue

        if not recent_filings:
            return {
                'ticker': ticker,
                'insider_sentiment': 0,
                'data_available': False,
                'reason': f'No filings in last {days} days'
            }

        # Count buys vs sells (simplified - based on title keywords)
        buys = 0
        sells = 0
        executive_buys = 0
        executive_sells = 0

        for filing in recent_filings:
            summary = (filing.get('summary') or '').lower()
            title = (filing.get('insider_title') or '').upper()

            is_executive = any(exec_title in title for exec_title in self.EXECUTIVE_TITLES)

            # Heuristic: Check summary for buy/sell indicators
            if 'acquisition' in summary or 'purchase' in summary:
                buys += 1
                if is_executive:
                    executive_buys += 1
            elif 'disposition' in summary or 'sale' in summary:
                sells += 1
                if is_executive:
                    executive_sells += 1

        total = buys + sells
        if total == 0:
            insider_sentiment = 0
        else:
            insider_sentiment = (buys - sells) / total

        # Detect clustering (3+ filings in 5 days)
        cluster_detected = self._detect_cluster(recent_filings)

        return {
            'ticker': ticker,
            'insider_sentiment': round(insider_sentiment, 3),
            'sentiment_label': self._sentiment_label(insider_sentiment),
            'data_available': True,
            'period_days': days,
            'total_filings': len(recent_filings),
            'buy_filings': buys,
            'sell_filings': sells,
            'executive_buys': executive_buys,
            'executive_sells': executive_sells,
            'cluster_detected': cluster_detected,
            'signal_strength': 'strong' if cluster_detected and abs(insider_sentiment) > 0.3 else 'moderate' if abs(insider_sentiment) > 0.2 else 'weak'
        }

    def _detect_cluster(self, filings: List[Dict], window_days: int = 5, min_filings: int = 3) -> bool:
        """Detect clustered insider activity."""
        if len(filings) < min_filings:
            return False

        dates = []
        for f in filings:
            if f.get('filed_date'):
                try:
                    dates.append(datetime.strptime(f['filed_date'], '%Y-%m-%d'))
                except ValueError:
                    continue

        dates.sort()

        for i in range(len(dates) - min_filings + 1):
            window_start = dates[i]
            count = 1
            for j in range(i + 1, len(dates)):
                if (dates[j] - window_start).days <= window_days:
                    count += 1
                else:
                    break

            if count >= min_filings:
                return True

        return False

    def _sentiment_label(self, sentiment: float) -> str:
        """Convert sentiment score to label."""
        if sentiment >= 0.5:
            return 'strong_bullish'
        elif sentiment >= 0.2:
            return 'bullish'
        elif sentiment <= -0.5:
            return 'strong_bearish'
        elif sentiment <= -0.2:
            return 'bearish'
        else:
            return 'neutral'


# Global instance
_fetcher = None


def get_sec_fetcher() -> SECInsiderFetcher:
    """Get or create the SEC fetcher instance."""
    global _fetcher
    if _fetcher is None:
        _fetcher = SECInsiderFetcher()
    return _fetcher


def get_insider_sentiment(ticker: str, days: int = 90) -> Dict:
    """Get insider sentiment for a ticker."""
    return get_sec_fetcher().get_insider_sentiment(ticker, days)


def search_insider_filings(ticker: str, count: int = 20) -> List[Dict]:
    """Search for recent insider filings."""
    return get_sec_fetcher().search_company_filings(ticker, count=count)
