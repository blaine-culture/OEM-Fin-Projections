from dataclasses import dataclass
from typing import Dict, Final

@dataclass
class CartConfig:
    COMPONENTS_COST: Final[float] = 76000
    LABOR_COST_PERCENTAGE: Final[float] = 0.25
    
    # Separated component costs and prices
    UTILITY_CART_COST: Final[float] = 3000
    UTILITY_CART_PRICE: Final[float] = 6000  # 50% margin
    
    TCU_COST: Final[float] = 5000
    TCU_PRICE: Final[float] = 6000  # 16.7% margin
    
    AUTOFILLER_COST: Final[float] = 3000
    AUTOFILLER_PRICE: Final[float] = 6000  # 50% margin

@dataclass
class ConsumablesConfig:
    INITIAL_VESSEL_COST: Final[float] = 325
    INITIAL_VESSEL_PRICE: Final[float] = 600
    SAFETY_FACTOR: Final[float] = 1.0
    
    # Autofiller pack pricing (consumable)
    INITIAL_AUTOFILLER_PACK_COST: Final[float] = 29
    INITIAL_AUTOFILLER_PACK_PRICE: Final[float] = 80
    
    INITIAL_INOCULATION_PACK_COST: Final[float] = 115
    INITIAL_INOCULATION_PACK_PRICE: Final[float] = 167

@dataclass
class SoftwareConfig:
    SUBSCRIPTION_PRICE: Final[float] = 10000  # Updated to $10,000
    SOFTWARE_COST_PERCENTAGE: Final[float] = 0.10  # 90% margin
    OPC_PRICE: Final[float] = 0
    SERVICE_CONTRACT_PERCENTAGE: Final[float] = 0.10
    OPC_ADOPTION_RATE: Final[float] = 0.0

@dataclass
class WarrantyConfig:
    PERCENTAGE: Final[float] = 0.10
    COST_PERCENTAGE: Final[float] = 0.50
    PERIOD: Final[int] = 1

@dataclass
class OperationalConfig:
    CART_UTILIZATION_PERCENTAGE: Final[float] = 0.80
    TOTAL_MARKET_BIOREACTORS: Final[int] = 15205
    MARKET_GROWTH: Final[float] = 0.14
    
    # Updated installation pricing
    INSTALLATION_PRICE: Final[float] = 10000  # $10,000 selling price
    INSTALLATION_COST: Final[float] = 5000  # $5,000 cost (50% margin)
    
    # Partner discount rates
    PARTNER_HARDWARE_DISCOUNT: Final[float] = 0.25  # 25% discount on hardware
    PARTNER_CONSUMABLES_DISCOUNT: Final[float] = 0.30  # 30% discount on consumables
    DIRECT_SALES_PERCENTAGE: Final[float] = 0.0  # Initially 0% direct sales

@dataclass
class FinancialConfig:
    INFLATION_RATE: Final[float] = 0.025
    INITIAL_SELLING_PRICE: Final[float] = 230000

@dataclass
class ProcessConfig:
    VESSEL_TYPES: Final[tuple] = ('Mammalian_Vessels', 'Mammalian_Glass_Vessels', 'AAV_Man_Vessels', 'AAV_Auto_Vessels')
    AAV_MAN_RUN_PERCENTAGE: Final[float] = 0.00
    AAV_AUTO_RUN_PERCENTAGE: Final[float] = 0.20
    MAMMALIAN_RUN_PERCENTAGE: Final[float] = 0.64
    MAMMALIAN_GLASS_RUN_PERCENTAGE: Final[float] = 0.16
    AAV_RUNS_PER_MONTH: Final[int] = 2
    MAMMALIAN_RUNS_PER_MONTH: Final[int] = 1

    @property
    def TOTAL_RUNS_PER_YEAR_PER_CART(self) -> float:
        return (self.AAV_RUNS_PER_MONTH * 12 * (self.AAV_MAN_RUN_PERCENTAGE + self.AAV_AUTO_RUN_PERCENTAGE) +
                self.MAMMALIAN_RUNS_PER_MONTH * 12 * (self.MAMMALIAN_RUN_PERCENTAGE + self.MAMMALIAN_GLASS_RUN_PERCENTAGE))

class Config:
    def __init__(self):
        self.cart = CartConfig()
        self.consumables = ConsumablesConfig()
        self.software = SoftwareConfig()
        self.warranty = WarrantyConfig()
        self.operational = OperationalConfig()
        self.financial = FinancialConfig()
        self.process = ProcessConfig()

    def to_dict(self) -> Dict:
        config_dict = {}
        for category in [self.cart, self.consumables, self.software, self.warranty, self.operational, self.financial, self.process]:
            for key, value in category.__dict__.items():
                if not key.startswith('_'):
                    config_dict[key] = value
        return config_dict