import pytest
from src.services.signal_parser import HinglishSignalParser, parser


class TestHinglishSignalParser:
    """Tests for the Hinglish signal parser."""
    
    def setup_method(self):
        self.parser = HinglishSignalParser()
    
    def test_parse_nifty_ce_buy(self):
        """Test parsing NIFTY CE BUY signal."""
        result = self.parser.parse("NIFTY 22500 CE BUY 22550 SL 22500")
        
        assert result is not None
        assert result.underlying == "NIFTY"
        assert result.strike == 22500
        assert result.option_type == "CE"
        assert result.action == "BUY"
        assert result.entry_price == 22550
        assert result.stop_loss == 22500
    
    def test_parse_banknifty_pe_sell(self):
        """Test parsing BANKNIFTY PE SELL signal."""
        result = self.parser.parse("BANK NIFTY 45000 PE SELL SL 45100")
        
        assert result is not None
        assert result.underlying == "BANKNIFTY"
        assert result.strike == 45000
        assert result.option_type == "PE"
        assert result.action == "SELL"
        assert result.stop_loss == 45100
    
    def test_parse_finnifty_call(self):
        """Test parsing FINNIFTY CALL signal."""
        result = self.parser.parse("FINNIFTY CE 22500 LELO 22550")
        
        assert result is not None
        assert result.underlying == "FINNIFTY"
        assert result.option_type == "CE"
        assert result.action == "BUY"
    
    def test_parse_with_target(self):
        """Test parsing with target price."""
        result = self.parser.parse("NIFTY 22500 CE BUY 22550 SL 22500 TARGET 22650")
        
        assert result is not None
        assert result.target == 22650
    
    def test_parse_hinglish_variations(self):
        """Test Hinglish variations like LELO, BECHO."""
        result = self.parser.parse("NIFTY 22500 CE LELO")
        
        assert result is not None
        assert result.action == "BUY"
    
    def test_parse_missing_underlying(self):
        """Test parsing with missing underlying."""
        result = self.parser.parse("BUY 22500 CE")
        
        assert result is None
    
    def test_confidence_calculation(self):
        """Test confidence score calculation."""
        result = self.parser.parse("NIFTY 22500 CE BUY 22550 SL 22500 TARGET 22650")
        
        assert result is not None
        assert result.confidence > 0.5


class TestSignalParserModule:
    """Tests for the module-level parser."""
    
    def test_parser_instance(self):
        """Test parser instance exists."""
        assert parser is not None
        assert isinstance(parser, HinglishSignalParser)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
