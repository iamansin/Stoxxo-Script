import unittest
import sys
from datetime import datetime, time
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))  # Adjust the path as needed
from core import TradingHoursValidator, OrderParser, OrderType, Exchange, ProductType, OptionType

class TestTradingHoursValidator(unittest.TestCase):
    def setUp(self):
        # Create validator with default settings (Mon-Fri, 9:15-15:30)
        self.validator = TradingHoursValidator()
        
    def test_trading_allowed_regular_hours(self):
        # Test during regular trading hours on a weekday
        test_datetime = datetime(2025, 10, 7, 10, 30)  # Tuesday 10:30 AM
        is_allowed, reason = self.validator.is_trading_allowed(test_datetime)
        self.assertTrue(is_allowed)
        self.assertEqual(reason, "Regular trading hours")
        
    def test_trading_not_allowed_weekend(self):
        # Test on weekend
        test_datetime = datetime(2025, 10, 5, 10, 30)  # Sunday 10:30 AM
        is_allowed, reason = self.validator.is_trading_allowed(test_datetime)
        self.assertFalse(is_allowed)
        self.assertTrue("Non-trading day" in reason)
        
    def test_trading_not_allowed_after_hours(self):
        # Test after market hours
        test_datetime = datetime(2025, 10, 7, 16, 0)  # Tuesday 4:00 PM
        is_allowed, reason = self.validator.is_trading_allowed(test_datetime)
        self.assertFalse(is_allowed)
        self.assertTrue("Outside trading hours" in reason)

class TestOrderParser(unittest.TestCase):
    def setUp(self):
        self.parser = OrderParser()
        
    def test_parse_symbol_details(self):
        symbol_str = "NIFTY 7TH OCT 25900 CE"
        index, expiry, strike, option_type = self.parser._parse_symbol_details(symbol_str)
        
        self.assertEqual(index, "NIFTY")
        self.assertEqual(expiry, "7TH OCT")
        self.assertEqual(strike, "25900")
        self.assertEqual(option_type, OptionType.CE)
        
    def test_parse_datetime(self):
        # Test basic time parsing
        time_str = "1:36:10:123"
        parsed_dt = self.parser._parse_datetime(time_str)
        
        self.assertEqual(parsed_dt.hour, 1)
        self.assertEqual(parsed_dt.minute, 36)
        self.assertEqual(parsed_dt.second, 10)
        self.assertEqual(parsed_dt.microsecond, 123000)
        
        # # Test parsing time from previous day
        # current_hour = datetime.now().hour
        # if current_hour < 12:  # It's morning now
        #     future_hour = current_hour + 2
        #     time_str = f"{future_hour:02d}:30:45:123"
        #     parsed_dt = self.parser._parse_datetime(time_str)
        #     self.assertEqual(parsed_dt.day, datetime.now().day - 1)  # Should be yesterday
        
    def test_process_valid_log_line(self):
        # Sample valid log line
        log_line = "1:42:10:123,TRADING,Initiating Order Placement; Symbol: NIFTY 7TH OCT 25900 CE; Leg ID: ABC123; Qty: 50; Txn: BUY,SIM1,false,TestPortfolio"
        
        order = self.parser.process_log_line(log_line)
        
        self.assertIsNotNone(order)
        self.assertEqual(order.order_id, "ABC123")
        self.assertEqual(order.strategy_tag, "SIM1")
        self.assertEqual(order.index, "NIFTY")
        self.assertEqual(order.strike, "25900")
        self.assertEqual(order.quantity, "50")
        self.assertEqual(order.expiry, "7TH OCT")
        self.assertEqual(order.order_type, OrderType.BUY)
        self.assertEqual(order.exchange, Exchange.NFO)
        self.assertEqual(order.product, ProductType.NRML)
        self.assertEqual(order.option_type, OptionType.CE)
        
    def test_process_invalid_log_line(self):
        # Test with invalid log line format
        invalid_log = "invalid,log,line"
        order = self.parser.process_log_line(invalid_log)
        self.assertIsNone(order)
        
    def test_validate_order_quantity(self):
        # Test with invalid quantity
        log_line = "14:30:45:123,TRADING,Initiating Order Placement; Symbol: NIFTY 7TH OCT 25900 CE; Leg ID: ABC123; Qty: 0; Txn: BUY,user123,false,TestPortfolio"
        order = self.parser.process_log_line(log_line)
        self.assertIsNone(order)  # Should return None due to invalid quantity

if __name__ == '__main__':
    unittest.main()