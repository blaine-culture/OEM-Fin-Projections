from dataclasses import dataclass
from typing import Dict, Final

@dataclass
class CartConfig:
    """
    Costs and end-customer prices for:
      - Base hardware (the main cart, excluding TCU/utility/autofiller)
      - TCU
      - Utility cart
      - Autofiller unit
    """
    # Base hardware (portion of the system = $212k at the end-customer level)
    COMPONENTS_COST: Final[float] = 76000  # manufacturing cost for the base hardware
    LABOR_COST_PERCENTAGE: Final[float] = 0.25
    # The model will treat 212k as the "base cart" price.
    # We'll set this in the FinancialConfig (see below) as INITIAL_SELLING_PRICE = 212000

    # TCU
    TCU_COST: Final[float] = 5000
    TCU_PRICE: Final[float] = 6000

    # Utility cart
    UTILITY_CART_COST: Final[float] = 3000
    UTILITY_CART_PRICE: Final[float] = 6000

    # Autofiller
    AUTOFILLER_COST: Final[float] = 3000
    AUTOFILLER_PRICE: Final[float] = 6000

@dataclass
class ConsumablesConfig:
    """Consumables costs and prices, including vessel and autofiller packs."""
    INITIAL_VESSEL_COST: Final[float] = 325
    INITIAL_VESSEL_PRICE: Final[float] = 600
    SAFETY_FACTOR: Final[float] = 1.0

    INITIAL_AUTOFILLER_PACK_COST: Final[float] = 29
    INITIAL_AUTOFILLER_PACK_PRICE: Final[float] = 80

    # If you still need inoculation packs, keep them here:
    INITIAL_INOCULATION_PACK_COST: Final[float] = 115
    INITIAL_INOCULATION_PACK_PRICE: Final[float] = 167

@dataclass
class SoftwareConfig:
    """
    Software revenue (100% margin).
    SERVICE_CONTRACT_PERCENTAGE is the fraction of hardware price 
    that becomes the annual service contract.
    """
    SUBSCRIPTION_PRICE: Final[float] = 10000  
    SERVICE_CONTRACT_PERCENTAGE: Final[float] = 0.10

@dataclass
class WarrantyConfig:
    """
    Warranty coverage (if still relevant).
    PERCENTAGE: portion of hardware price that is allocated to warranty
    COST_PERCENTAGE: portion of that revenue spent on coverage
    PERIOD: years or months of coverage (your use may vary)
    """
    PERCENTAGE: Final[float] = 0.10
    COST_PERCENTAGE: Final[float] = 0.50
    PERIOD: Final[int] = 1

@dataclass
class OperationalConfig:
    """Operational parameters for partner discounts, installation, etc."""
    CART_UTILIZATION_PERCENTAGE: Final[float] = 0.80
    PARTNER_HARDWARE_DISCOUNT: Final[float] = 0.25
    PARTNER_CONSUMABLES_DISCOUNT: Final[float] = 0.30

    # Installation
    INSTALLATION_PRICE: Final[float] = 10000
    INSTALLATION_COST: Final[float] = 5000

    # Direct sales
    DIRECT_SALES_PERCENTAGE: Final[float] = 0.0

    # The portion of service revenue that goes to cost:
    SERVICE_COST_RATIO: Final[float] = 0.40

@dataclass
class FinancialConfig:
    """
    Financial parameters.
    INITIAL_SELLING_PRICE here is set to 212,000 
    so that the base hardware + TCU + utility cart + autofiller 
    sum to 230k at the end-customer level (212 + 6 + 6 + 6).
    """
    INFLATION_RATE: Final[float] = 0.025
    INITIAL_SELLING_PRICE: Final[float] = 212000  # The base cart portion

@dataclass
class ProcessConfig:
    """
    Defines how many runs occur per cart and how those runs are split 
    among different vessel types (Mammalian vs. AAV).
    """
    VESSEL_TYPES: Final[tuple] = (
        'Mammalian_Vessels',
        'Mammalian_Glass_Vessels',
        'AAV_Man_Vessels',
        'AAV_Auto_Vessels'
    )
    AAV_MAN_RUN_PERCENTAGE: Final[float] = 0.00
    AAV_AUTO_RUN_PERCENTAGE: Final[float] = 0.20
    MAMMALIAN_RUN_PERCENTAGE: Final[float] = 0.64
    MAMMALIAN_GLASS_RUN_PERCENTAGE: Final[float] = 0.16

    AAV_RUNS_PER_MONTH: Final[int] = 2
    MAMMALIAN_RUNS_PER_MONTH: Final[int] = 1

    @property
    def TOTAL_RUNS_PER_YEAR_PER_CART(self) -> float:
        """
        Calculated runs per year per cart,
        factoring in monthly runs and usage percentages.
        """
        return (
            self.AAV_RUNS_PER_MONTH * 12
            * (self.AAV_MAN_RUN_PERCENTAGE + self.AAV_AUTO_RUN_PERCENTAGE)
            + self.MAMMALIAN_RUNS_PER_MONTH * 12
            * (self.MAMMALIAN_RUN_PERCENTAGE + self.MAMMALIAN_GLASS_RUN_PERCENTAGE)
        )

class Config:
    """Main config class bundling all dataclasses."""
    def __init__(self):
        self.cart = CartConfig()
        self.consumables = ConsumablesConfig()
        self.software = SoftwareConfig()
        self.warranty = WarrantyConfig()
        self.operational = OperationalConfig()
        self.financial = FinancialConfig()
        self.process = ProcessConfig()

    def to_dict(self) -> Dict:
        """
        Return a single dictionary with all config fields, 
        which can be useful for debugging/logging.
        """
        config_dict = {}
        for category in [
            self.cart,
            self.consumables,
            self.software,
            self.warranty,
            self.operational,
            self.financial,
            self.process
        ]:
            for key, value in category.__dict__.items():
                if not key.startswith('_'):
                    config_dict[key] = value
        return config_dict
