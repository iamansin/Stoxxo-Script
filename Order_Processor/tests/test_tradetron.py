import requests
import asyncio
import httpx
from datetime import datetime

class TradetronFormatter:
    """
    Class to format trading parameters for Tradetron API requests
    Supports BUY_CE, SELL_CE, BUY_PE, SELL_PE trade types
    """
    
    VALID_TRADE_TYPES = ["BUY_CE", "SELL_CE", "BUY_PE", "SELL_PE"]
    
    def __init__(self, base_url, auth_token):
        self.base_url = base_url
        self.auth_token = auth_token
    
    def format_params(self, trade_type, trades_data):
        """
        Format trading parameters into the required key-value structure
        
        Args:
            trade_type (str): One of BUY_CE, SELL_CE, BUY_PE, SELL_PE
            trades_data (list): List of dictionaries containing trade information
                               Each dict should have: strike, expiry, quantity
        
        Returns:
            dict: Formatted parameters ready for API request
        
        Example:
            trades_data = [
                {"strike": "25300", "expiry": "2025-10-20", "quantity": "75"},
                {"strike": "25400", "expiry": "2025-10-20", "quantity": "75"},
            ]
        """
        if trade_type not in self.VALID_TRADE_TYPES:
            raise ValueError(f"Invalid trade_type. Must be one of {self.VALID_TRADE_TYPES}")
        
        params = {'auth-token': self.auth_token}
        
        # Extract option type (CE or PE) from trade_type
        option_type = trade_type.split('_')[1]  # Gets 'CE' or 'PE'
        
        # First key-value pair is the trade type with value 1
        params['key1'] = trade_type
        params['value1'] = 1
        
        # Start counter at 2 for subsequent keys
        key_counter = 2
        
        # Format each trade
        for idx, trade in enumerate(trades_data, start=1):
            # Strike
            params[f'key{key_counter}'] = f"Strike_{option_type}_Buy{idx}"
            params[f'value{key_counter}'] = str(trade['strike'])
            key_counter += 1
            
            # Expiry
            params[f'key{key_counter}'] = f"Expiry_{option_type}_Buy{idx}"
            params[f'value{key_counter}'] = trade['expiry']
            key_counter += 1
            
            # Quantity
            params[f'key{key_counter}'] = f"Quantity_{option_type}_Buy{idx}"
            params[f'value{key_counter}'] = str(trade['quantity'])
            key_counter += 1

        return params
    
    def send_request(self, trade_type, trades_data):
        """
        Format parameters and send GET request to Tradetron API
        
        Args:
            trade_type (str): One of BUY_CE, SELL_CE, BUY_PE, SELL_PE
            trades_data (list): List of dictionaries containing trade information
        
        Returns:
            dict: Response from API or error information
        """
        try:
            params = self.format_params(trade_type, trades_data)
            
            print(f"Request URL: {self.base_url}")
            print(f"Parameters: {params}")
            print("-" * 80)

            response = requests.get(self.base_url, params=params)
            
            print(f"Full URL: {response.url}")
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                print("Success!")
                
                # Try to parse JSON, but handle non-JSON responses
                try:
                    json_data = response.json()
                    return {
                        'success': True,
                        'data': json_data,
                        'url': response.url
                    }
                except ValueError:
                    # Response is not JSON
                    return {
                        'success': True,
                        'data': response.text,
                        'url': response.url,
                        'note': 'Response was not JSON format'
                    }
            else:
                    print(f"Error: {response.text}")
                    return {
                        'success': False,
                        'error': response.text,
                        'status_code': response.status_code
                    }
                
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
        except Exception as e:
            print(f"Error: {e}")
            return {
                'success': False,
                'error': str(e)
            }


# Example usage
def main():
    # Initialize formatter
    formatter = TradetronFormatter(
        base_url="https://api.tradetron.tech/api",
        auth_token="6d51e02b-f0dd-4bed-b4c9-525669b65e6c"
    )
    
    # Example 1: BUY_CE with 3 trades
    print("Example 1: BUY_CE with 3 trades")
    print("=" * 80)
    trades_ce = [
        {"strike": "25300", "expiry": "2025-10-20", "quantity": "75"},
        {"strike": "25400", "expiry": "2025-10-20", "quantity": "75"},
        {"strike": "25450", "expiry": "2025-10-20", "quantity": "75"},
    ]
    result1 = formatter.send_request("BUY_CE", trades_ce)
    print("\n")
    
    # Example 2: SELL_PE with 2 trades
    print("Example 2: BUY_PE with 2 trades")
    print("=" * 80)
    trades_pe = [
       {"strike": "25300", "expiry": "2025-10-20", "quantity": "75"},
        {"strike": "25400", "expiry": "2025-10-20", "quantity": "75"},
        {"strike": "25450", "expiry": "2025-10-20", "quantity": "75"},
    ]
    result2 = formatter.send_request("BUY_PE", trades_pe)
    print("\n")
    
    # Example 3: Just format params without sending (useful for debugging)
    print("Example 3: Format params only (no API call)")
    print("=" * 80)
    trades_single = [
        {"strike": "19000", "expiry": "2025-10-20", "quantity": "50"},
    ]
    params_only = formatter.format_params("BUY_CE", trades_single)
    print("Formatted parameters:")
    for key, val in params_only.items():
        print(f"  {key}: {val}")


if __name__ == "__main__":
    main()