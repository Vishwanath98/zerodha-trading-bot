import csv
import io
from typing import List
from src.services.signal_parser import parser
from src.core.logger import logger


class CSVAdapter:
    """
    CSV file adapter for bulk signal import.
    Format: underlying,strike,option_type,action,entry_price,stop_loss,target,qty
    """
    
    def parse_csv(self, csv_content: str) -> List[dict]:
        """Parse CSV content into signal dictionaries."""
        signals = []
        
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            
            for row in reader:
                try:
                    underlying = row.get('underlying', '').strip()
                    action = row.get('action', 'BUY').strip().upper()
                    strike = row.get('strike')
                    option_type = row.get('option_type')
                    entry_price = row.get('entry_price')
                    stop_loss = row.get('stop_loss')
                    target = row.get('target')
                    quantity = row.get('quantity')
                    
                    if strike:
                        strike = int(strike)
                    if entry_price:
                        entry_price = float(entry_price)
                    if stop_loss:
                        stop_loss = float(stop_loss)
                    if target:
                        target = float(target)
                    if quantity:
                        quantity = int(quantity)
                    
                    signal_text = f"{underlying}"
                    if strike:
                        signal_text += f" {strike}"
                    if option_type:
                        signal_text += f" {option_type}"
                    signal_text += f" {action}"
                    if entry_price:
                        signal_text += f" {entry_price}"
                    if stop_loss:
                        signal_text += f" SL {stop_loss}"
                    if target:
                        signal_text += f" TARGET {target}"
                    
                    signals.append({
                        'raw_message': signal_text,
                        'source': 'csv',
                        'parsed': {
                            'underlying': underlying,
                            'strike': strike,
                            'option_type': option_type,
                            'action': action,
                            'entry_price': entry_price,
                            'stop_loss': stop_loss,
                            'target': target,
                            'quantity': quantity
                        }
                    })
                    
                except Exception as e:
                    logger.error(f"Error parsing CSV row: {e}")
                    continue
            
            logger.info(f"Parsed {len(signals)} signals from CSV")
            
        except Exception as e:
            logger.error(f"Error parsing CSV: {e}")
        
        return signals
    
    def generate_csv_template(self) -> str:
        """Generate CSV template for users."""
        headers = "underlying,strike,option_type,action,entry_price,stop_loss,target,qty\n"
        sample = "NIFTY,22500,CE,BUY,22550,22500,22650,1\n"
        sample += "BANKNIFTY,45000,PE,SELL,44950,45100,44800,1\n"
        sample += "FINNIFTY,22500,CE,BUY,,22500,22600,1\n"
        
        return headers + sample


csv_adapter = CSVAdapter()
