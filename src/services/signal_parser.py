import re
from typing import Optional
from dataclasses import dataclass
from src.core.logger import logger


@dataclass
class ParsedSignal:
    underlying: str  # NIFTY, BANKNIFTY, FINNIFTY, etc.
    strike: Optional[int]
    option_type: Optional[str]  # CE or PE
    expiry: Optional[str]  # weekly, monthly
    action: str  # BUY, SELL
    entry_price: Optional[float]
    stop_loss: Optional[float]
    target: Optional[float]
    quantity: Optional[int]
    confidence: float
    raw_terms: list


class HinglishSignalParser:
    """
    Parser for Hinglish trading signals from Telegram groups.
    Examples:
    - "NIFTY 22500 CE LELO 22550 SL"
    - "BANK NIFTY BUY 45000 PE AT 450 SL 44800"
    - "FINNIFTY CE 22500 ABOVE 22600 TGT 22800"
    """
    
    UNDERLYING_PATTERNS = [
        r'\b(NIFTY|BANK\s*NIFTY|BANKNIFTY|FINNIFTY|FIN\s*NIFTY|NIFTY\s*50|NF|BN|FNF)\b',
        r'\b(RELIANCE|INFY|TCS|WIPRO|HDFC|ICICI|AXISBANK|BAJFINANCE|ADANIPORTS)\b',
        r'\bSENSEX\b',
    ]
    
    ACTION_PATTERNS = [
        r'(BUY|BUY\s*NOW|LONG|LELO|LE\s*GE|TAKE\s*LONG|GO\s*LONG)',
        r'(SELL|SHORT|SELL\s*NOW|BECHO|BE\s*CHUKI|TAKE\s*SHORT|GO\s*SHORT)',
    ]
    
    OPTION_TYPE_PATTERNS = [
        r'\b(CE|CALL|PUT|PE)\b',
    ]
    
    PRICE_PATTERNS = [
        r'(?:AT|@|₹|RS\.?|RUPEES?)?\s*(\d+(?:\.\d+)?)',
    ]
    
    SL_PATTERN = r'(?:SL|STOP\s*LOSS|STOPLOSS)[:\s]*(\d+(?:\.\d+)?)'
    TARGET_PATTERN = r'(?:TARGET|TGT|TP)[:\s]*(\d+(?:\.\d+)?)'
    QUANTITY_PATTERN = r'(?:QTY|QUANTITY|Q)[:\s]*(\d+)'
    
    EXPIRY_PATTERNS = [
        r'\b(WEEKLY|WEEK|THIS\s*WEEK|CURRENT\s*WEEK)\b',
        r'\b(MONTHLY|MONTH|EXPIRY)\b',
        r'\b(NEXT\s*WEEK|NEXT)\b',
    ]
    
    def __init__(self):
        self.underlying_re = re.compile('|'.join(self.UNDERLYING_PATTERNS), re.IGNORECASE)
        self.action_re = re.compile('|'.join(self.ACTION_PATTERNS), re.IGNORECASE)
        self.option_re = re.compile('|'.join(self.OPTION_TYPE_PATTERNS), re.IGNORECASE)
        self.price_re = re.compile('|'.join(self.PRICE_PATTERNS))
        self.sl_re = re.compile(self.SL_PATTERN, re.IGNORECASE)
        self.target_re = re.compile(self.TARGET_PATTERN, re.IGNORECASE)
        self.qty_re = re.compile(self.QUANTITY_PATTERN, re.IGNORECASE)
        self.expiry_re = re.compile('|'.join(self.EXPIRY_PATTERNS), re.IGNORECASE)
    
    def normalize_text(self, text: str) -> str:
        """Normalize common Hinglish variations."""
        text = text.upper()
        
        replacements = {
            'LELO': 'BUY',
            'LE GE': 'BUY',
            'BECHO': 'SELL',
            'BE CHUKI': 'SELL',
            'CALL': 'CE',
            'PUT': 'PE',
            'LONG': 'BUY',
            'SHORT': 'SELL',
        }
        
        for k, v in replacements.items():
            text = re.sub(r'\b' + k + r'\b', v, text, flags=re.IGNORECASE)
        
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def extract_underlying(self, text: str) -> Optional[str]:
        """Extract the underlying asset."""
        match = self.underlying_re.search(text)
        if match:
            underlying = match.group(1).upper()
            underlying = underlying.replace(' ', '')
            
            mapping = {
                'BANKNIFTY': 'BANKNIFTY',
                'BANK': 'BANKNIFTY',
                'FINNIFTY': 'FINNIFTY',
                'FIN': 'FINNIFTY',
                'NF': 'NIFTY',
                'BN': 'BANKNIFTY',
                'FNF': 'FINNIFTY',
                'NIFTY50': 'NIFTY',
                'NIFTY 50': 'NIFTY',
            }
            return mapping.get(underlying, underlying)
        return None
    
    def extract_action(self, text: str) -> str:
        """Extract BUY or SELL."""
        match = self.action_re.search(text)
        if match:
            groups = match.groups()
            action = groups[0] or groups[1]
            if action:
                action = action.upper()
                if action in ['BUY', 'LONG', 'LELO', 'LE GE', 'TAKE LONG', 'GO LONG']:
                    return 'BUY'
                return 'SELL'
        return 'BUY'
    
    def extract_option_type(self, text: str) -> Optional[str]:
        """Extract CE or PE."""
        match = self.option_re.search(text)
        if match:
            opt = match.group(1).upper()
            return 'CE' if opt == 'CE' else 'PE'
        return None
    
    def extract_strike(self, text: str, default_underlying: Optional[str] = None) -> Optional[int]:
        """Extract strike price from text."""
        numbers = self.price_re.findall(text)
        
        if default_underlying in ['NIFTY', 'BANKNIFTY', 'FINNIFTY']:
            for num in numbers:
                val = int(float(num))
                if 10000 <= val <= 50000:
                    return val
        else:
            if numbers:
                return int(float(numbers[0]))
        
        return None
    
    def extract_prices(self, text: str, strike: Optional[int] = None) -> tuple:
        """Extract entry, SL, and target prices."""
        prices = self.price_re.findall(text)
        prices = [float(p) for p in prices]
        
        sl_match = self.sl_re.search(text)
        target_match = self.target_re.search(text)
        
        sl = float(sl_match.group(1)) if sl_match else None
        target = float(target_match.group(1)) if target_match else None
        
        filtered_prices = [p for p in prices if strike is None or int(p) != strike]
        
        entry = filtered_prices[0] if filtered_prices else None
        
        return entry, sl, target
    
    def extract_quantity(self, text: str) -> Optional[int]:
        """Extract quantity."""
        match = self.qty_re.search(text)
        if match:
            return int(match.group(1))
        return None
    
    def extract_expiry(self, text: str) -> Optional[str]:
        """Extract expiry type."""
        match = self.expiry_re.search(text)
        if match:
            exp = match.group(1).upper()
            if 'WEEK' in exp:
                return 'weekly'
            elif 'MONTH' in exp:
                return 'monthly'
        return None
    
    def calculate_confidence(self, parsed: ParsedSignal) -> float:
        """Calculate confidence score based on completeness."""
        score = 0.0
        total = 7.0
        
        if parsed.underlying:
            score += 1.0
        if parsed.action:
            score += 1.0
        if parsed.option_type or parsed.underlying in ['NIFTY', 'BANKNIFTY', 'FINNIFTY']:
            score += 1.0
        if parsed.strike:
            score += 1.0
        if parsed.entry_price:
            score += 1.0
        if parsed.stop_loss:
            score += 1.0
        if parsed.target:
            score += 1.0
        
        return score / total
    
    def parse(self, raw_message: str) -> Optional[ParsedSignal]:
        """Parse raw signal message into structured signal."""
        try:
            normalized = self.normalize_text(raw_message)
            
            underlying = self.extract_underlying(normalized)
            action = self.extract_action(normalized)
            option_type = self.extract_option_type(normalized)
            strike = self.extract_strike(normalized, underlying)
            entry_price, stop_loss, target = self.extract_prices(normalized, strike)
            quantity = self.extract_quantity(normalized)
            expiry = self.extract_expiry(normalized)
            
            if not underlying:
                logger.warning(f"Could not extract underlying from: {raw_message}")
                return None
            
            if not option_type and underlying in ['NIFTY', 'BANKNIFTY', 'FINNIFTY']:
                logger.warning(f"Could not extract option type from: {raw_message}")
                return None
            
            parsed = ParsedSignal(
                underlying=underlying,
                strike=strike,
                option_type=option_type,
                expiry=expiry,
                action=action,
                entry_price=entry_price,
                stop_loss=stop_loss,
                target=target,
                quantity=quantity,
                confidence=0.0,
                raw_terms=[]
            )
            
            parsed.confidence = self.calculate_confidence(parsed)
            
            logger.info(f"Parsed signal: {parsed}")
            return parsed
            
        except Exception as e:
            logger.error(f"Error parsing signal: {e}")
            return None


parser = HinglishSignalParser()
