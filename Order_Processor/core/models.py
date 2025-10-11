import json
import os
from typing import Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum
import uuid
from loguru import logger

class ExpiryMonth(Enum):
    CURRENT = 1
    NEXT = 2 
    NEXT2NEXT = 3

class OrderStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"

class OptionType(Enum):
    CE = 1
    PE = 0

class OrderType(Enum):
    BUY = "BUY"
    SELL = "SELL"

class Exchange(Enum):
    NFO = "NFO"
    BFO = "BFO"

class ProductType(Enum):
    MIS = "MIS"
    NRML = "NRML"

class Providers(Enum):
    TRADETRON = "tradetron"
    ALGOTRADES = "algotrades"
    ZERODHA = "zerodha"
    BINANCE = "binance"
    COINBASE = "coinbase"

class OrderObj(BaseModel):
    order_id: str
    strategy_tag: str
    index : str
    strike : str
    quantity : str
    expiry : Union[str | ExpiryMonth]
    order_type : OrderType
    exchange : Exchange
    product : ProductType
    option_type : OptionType
    actual_time : datetime
    parse_time : datetime
    stoxxo_order : str
    monthly_expiry : bool = False
    mapped_order : Optional[Dict[str, Any]] = None
    adapter_name : Optional[str] = None
    processing_gap: int  # in milliseconds(parse_time - actual_time)
    sent_time : datetime = None
    pipeline_latency : int = None  # in milliseconds(sent_time - parse_time)
    end_to_end_latency : int = None  # in milliseconds(sent_time - actual_time)
    status : OrderStatus = OrderStatus.PENDING  
    error_message : Optional[str] = None

    def __init__(self, **data: Any):
        if 'order_id' not in data:
            data['order_id'] = str(uuid.uuid4())
        super().__init__(**data)

    def update_object(self, update_data: Dict[str, Any]):
        for key, value in update_data.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else: raise AttributeError(f"{key} is not a valid attribute of OrderObj")
        return self

    def get_summary(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "strategy": self.strategy_tag,
            "index": self.index,
            "strike": self.strike,
            "quantity": self.quantity,
            "expiry": self.expiry,
            "order_type": self.order_type.value,
            "exchange": self.exchange.value,
            "product": self.product.value,
            "option_type": self.option_type.value,  # Convert enum to value
        }
    
    def dump_data_to_log(self, provider : Providers):
        try:
            # Calculate latencies only if sent_time exists and is valid
            if self.sent_time and isinstance(self.sent_time, datetime):
                end_to_end_latency = int((self.sent_time - self.actual_time).total_seconds() * 1000)
                pipeline_latency = int((self.sent_time - self.parse_time).total_seconds() * 1000)
            else:
                end_to_end_latency = None
                pipeline_latency = None

            info = json.dumps({
                "stoxxo_timestamp": self.actual_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                "stoxxo_latency": f"{self.processing_gap}ms",
                "receive_timestamp": self.parse_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                "sent_timestamp": self.sent_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] if self.sent_time else None,
                "pipeline_latency": f"{pipeline_latency}ms" if pipeline_latency is not None else None,
                "end_to_end_latency": f"{end_to_end_latency}ms" if end_to_end_latency is not None else None,
                "stoxxo_order": self.stoxxo_order,
                "order_summary": self.get_summary(),
                "mapped_order": self.mapped_order if self.mapped_order else {},
                "order_status": self.status.value,
                "error_message": self.error_message if self.error_message else 'None'
            })
            if provider == Providers.TRADETRON:
                logger.bind(tradetron=True).info(info)

            elif provider == Providers.ALGOTRADES:
                logger.bind(algotrades=True).info(info)

            logger.bind(order=True).info(info)
            return 
        
        except Exception as e:
            logger.error(f"Error while logging order data: {e}")
            return

