from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
from config import Config

class FinancialModel:
    """Financial model that tracks the full value chain from manufacturer to end customer."""
    
    def __init__(self, config: Config):
        self.config = config
        
    def _initialize_dataframe(self, start_year: int, start_month: int, projection_years: int = 5) -> pd.DataFrame:
        """Initialize DataFrame with monthly granularity for projection based on start date."""
        # Calculate ending date
        end_year = start_year + projection_years
        end_month = start_month - 1
        if end_month == 0:
            end_year -= 1
            end_month = 12
        
        # Generate all months in the range
        years = range(start_year, end_year + 1)
        months = range(1, 13)
        data = [(year, month) for year in years for month in months]
        df = pd.DataFrame(data, columns=['Year', 'Month'])
        
        # Filter to include only the projection period starting from start_date
        start_date = start_year * 12 + start_month
        end_date = end_year * 12 + end_month
        df['Date_Value'] = df['Year'] * 12 + df['Month']
        df = df[(df['Date_Value'] >= start_date) & (df['Date_Value'] <= end_date)]
        
        # Calculate relative year and month
        df['Months_From_Start'] = df['Date_Value'] - start_date
        df['Relative_Year'] = (df['Months_From_Start'] // 12) + 1
        df['Relative_Month'] = (df['Months_From_Start'] % 12) + 1
        
        # Add quarter information
        df['Quarter'] = ((df['Month'] - 1) // 3) + 1
        df['Month_in_Quarter'] = ((df['Month'] - 1) % 3) + 1
        
        # Format year-month for display
        df['Year_Month'] = df.apply(lambda x: f"{x['Year']}-{x['Month']:02d}", axis=1)
        
        # Calculate year fraction for inflation
        start_date_fraction = start_year + (start_month - 1) / 12
        df['Year_Fraction'] = df.apply(lambda x: (x['Year'] + (x['Month'] - 1) / 12) - start_date_fraction, axis=1)
        
        return df.reset_index(drop=True)
    
    def _apply_inflation_and_reduction(self, initial_value: float, year_fraction: float, cost_reduction: float, 
                                    apply_inflation: bool, apply_reduction: bool) -> float:
        """Apply inflation and cost reduction over time based on flags."""
        inflation_factor = (1 + self.config.financial.INFLATION_RATE) ** year_fraction if apply_inflation else 1.0
        reduction_factor = (1 - (cost_reduction * year_fraction)) if apply_reduction else 1.0
        return initial_value * inflation_factor * reduction_factor
    
    def _calculate_cart_sales(self, df: pd.DataFrame, scenario: Dict[str, Any]) -> pd.DataFrame:
        """Calculate cart sales for direct and partner channels based on scenario."""
        # Initialize cart columns
        df['Total_Carts'] = 0
        df['Direct_Carts'] = 0
        df['Partner_Carts'] = 0
        
        # Get sales projections by relative year
        partner_sales_by_year = scenario['partner_sales_by_year']
        direct_sales_by_year = scenario.get('direct_sales_by_year', {1: 0, 2: 0, 3: 0, 4: 0, 5: 0})
        
        # Distribution within each year
        quarter_distribution = {1: 0.15, 2: 0.20, 3: 0.25, 4: 0.40}
        month_in_quarter_distribution = {1: 0.20, 2: 0.30, 3: 0.50}
        
        # For each relative year, distribute sales across months
        for rel_year in range(1, 6):  # Assuming 5-year projection
            if rel_year in partner_sales_by_year:
                yearly_partner_carts = partner_sales_by_year[rel_year]
                yearly_direct_carts = direct_sales_by_year.get(rel_year, 0)
                
                # Distribute by quarter and month
                for quarter in range(1, 5):
                    quarter_pct = quarter_distribution[quarter]
                    for month_in_quarter in range(1, 4):
                        month_pct = month_in_quarter_distribution[month_in_quarter]
                        
                        # Calculate monthly sales
                        monthly_partner_carts = round(yearly_partner_carts * quarter_pct * month_pct)
                        monthly_direct_carts = round(yearly_direct_carts * quarter_pct * month_pct)
                        
                        # Find the corresponding row in dataframe
                        rel_month = (quarter - 1) * 3 + month_in_quarter
                        mask = (df['Relative_Year'] == rel_year) & (df['Relative_Month'] == rel_month)
                        
                        # Apply to the DataFrame
                        if any(mask):
                            df.loc[mask, 'Partner_Carts'] = monthly_partner_carts
                            df.loc[mask, 'Direct_Carts'] = monthly_direct_carts
        
        # Calculate cumulative values
        df['Monthly_New_Carts'] = df['Direct_Carts'] + df['Partner_Carts']
        df['Total_Carts'] = df['Monthly_New_Carts'].cumsum()
        df['Cumulative_Direct_Carts'] = df['Direct_Carts'].cumsum() 
        df['Cumulative_Partner_Carts'] = df['Partner_Carts'].cumsum()
        
        return df
    
    def _calculate_pricing(self, df: pd.DataFrame, scenario: Dict[str, Any]) -> pd.DataFrame:
        """Calculate pricing across the value chain with separate component pricing."""
        # Get inflation and reduction flags from scenario
        apply_inflation = scenario.get('apply_inflation', True)
        apply_reduction = scenario.get('apply_reduction', True)
        
        # Calculate base selling price with inflation adjustments
        df['Base_Selling_Price'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.financial.INITIAL_SELLING_PRICE, 
                x['Year_Fraction'], 
                0,
                apply_inflation,
                False  # No reduction for selling price
            ),
            axis=1
        )
        
        # Apply selling price reduction from scenario
        df['End_Customer_Hardware_Price'] = df['Base_Selling_Price']
        for rel_year, reduction in scenario.get('selling_price_reduction_by_year', {}).items():
            df.loc[df['Relative_Year'] == rel_year, 'End_Customer_Hardware_Price'] *= (1 - reduction)
        
        # Calculate our costs with inflation for each component
        df['Hardware_Manufacturing_Cost'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.cart.COMPONENTS_COST * (1 + self.config.cart.LABOR_COST_PERCENTAGE),
                x['Year_Fraction'],
                scenario['cost_reduction'],
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )
        
        # Calculate utility cart costs and prices with inflation
        df['Utility_Cart_Mfg_Cost'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.cart.UTILITY_CART_COST,
                x['Year_Fraction'],
                scenario['cost_reduction'],
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )
        
        df['Utility_Cart_End_Price'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.cart.UTILITY_CART_PRICE,
                x['Year_Fraction'],
                0,
                apply_inflation,
                False
            ),
            axis=1
        )
        
        # Calculate TCU costs and prices with inflation
        # IMPORTANT: Using TCU_Mfg_Cost consistently
        df['TCU_Mfg_Cost'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.cart.TCU_COST,
                x['Year_Fraction'],
                scenario['cost_reduction'],
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )
        
        df['TCU_End_Price'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.cart.TCU_PRICE,
                x['Year_Fraction'],
                0,
                apply_inflation,
                False
            ),
            axis=1
        )
        
        # For TCU, there's no transfer price - it's purchased by the partner directly
        df['TCU_Partner_Price'] = df['TCU_End_Price']  # Direct cost to partner
        
        # Calculate Autofiller unit costs and prices with inflation
        df['Autofiller_Unit_Mfg_Cost'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.cart.AUTOFILLER_COST,
                x['Year_Fraction'],
                scenario['cost_reduction'],
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )
        
        df['Autofiller_Unit_End_Price'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.cart.AUTOFILLER_PRICE,
                x['Year_Fraction'],
                0,
                apply_inflation,
                False
            ),
            axis=1
        )
        
        # Total hardware cost now includes core components cost + utility cart + TCU
        df['Total_Hardware_Manufacturing_Cost'] = df['Hardware_Manufacturing_Cost'] + df['Utility_Cart_Mfg_Cost'] + df['TCU_Mfg_Cost']
        
        # Our sell price to partner (with partner discount)
        df['Hardware_Partner_Price'] = df['End_Customer_Hardware_Price'] * (1 - self.config.operational.PARTNER_HARDWARE_DISCOUNT)
        df['Utility_Cart_Partner_Price'] = df['Utility_Cart_End_Price'] * (1 - self.config.operational.PARTNER_HARDWARE_DISCOUNT)
        df['Autofiller_Unit_Partner_Price'] = df['Autofiller_Unit_End_Price'] * (1 - self.config.operational.PARTNER_CONSUMABLES_DISCOUNT)
        
        # Software pricing - updated for 90% margin
        df['End_Customer_Software_Price'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.software.SUBSCRIPTION_PRICE, 
                x['Year_Fraction'], 
                0,
                apply_inflation,
                False
            ),
            axis=1
        )
        
        # Software cost is 10% of the price (90% margin)
        df['Software_Our_Cost'] = df['End_Customer_Software_Price'] * self.config.software.SOFTWARE_COST_PERCENTAGE
        
        # We get 100% of software revenue - not going through partner
        df['Software_Partner_Price'] = 0  # Partner doesn't receive this revenue
        
        df['Software_Year_Fraction'] = (13 - df['Month']) / 12
        df['Software_Revenue_Factor'] = df.apply(lambda x: x['Software_Year_Fraction'] if x['Month'] > 1 else 1, axis=1)
        
        # Consumables pricing
        df['End_Customer_Vessel_Price'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.consumables.INITIAL_VESSEL_PRICE, 
                x['Year_Fraction'], 
                0,
                apply_inflation,
                False
            ),
            axis=1
        )
        
        df['Vessel_Manufacturing_Cost'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.consumables.INITIAL_VESSEL_COST, 
                x['Year_Fraction'], 
                scenario['cost_reduction'],
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )
        
        df['Vessel_Partner_Price'] = df['End_Customer_Vessel_Price'] * (1 - self.config.operational.PARTNER_CONSUMABLES_DISCOUNT)
        
        # Autofiller pack pricing
        df['End_Customer_Autofiller_Pack_Price'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.consumables.INITIAL_AUTOFILLER_PACK_PRICE, 
                x['Year_Fraction'], 
                0,
                apply_inflation,
                False
            ),
            axis=1
        )
        
        df['Autofiller_Pack_Mfg_Cost'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.consumables.INITIAL_AUTOFILLER_PACK_COST, 
                x['Year_Fraction'], 
                scenario['cost_reduction'],
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )
        
        df['Autofiller_Pack_Partner_Price'] = df['End_Customer_Autofiller_Pack_Price'] * (1 - self.config.operational.PARTNER_CONSUMABLES_DISCOUNT)
        
        # Installation pricing
        df['Installation_End_Price'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.operational.INSTALLATION_PRICE, 
                x['Year_Fraction'], 
                0,
                apply_inflation,
                False
            ),
            axis=1
        )
        
        df['Installation_Our_Cost'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.operational.INSTALLATION_COST, 
                x['Year_Fraction'], 
                scenario['cost_reduction'],
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )
        
        return df
    
    def _calculate_consumables(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate consumables usage and distribution."""
        # Calculate monthly runs
        df['Monthly_Runs'] = (df['Total_Carts'] * 4 *
                             (self.config.process.TOTAL_RUNS_PER_YEAR_PER_CART / 12) *
                             self.config.operational.CART_UTILIZATION_PERCENTAGE)
        
        # Calculate vessel distribution
        df['Mammalian_Vessels'] = df['Monthly_Runs'] * self.config.process.MAMMALIAN_RUN_PERCENTAGE
        df['Mammalian_Glass_Vessels'] = df['Monthly_Runs'] * self.config.process.MAMMALIAN_GLASS_RUN_PERCENTAGE
        df['AAV_Man_Vessels'] = df['Monthly_Runs'] * self.config.process.AAV_MAN_RUN_PERCENTAGE
        df['AAV_Auto_Vessels'] = df['Monthly_Runs'] * self.config.process.AAV_AUTO_RUN_PERCENTAGE
        df['Total_Vessels'] = (df['Mammalian_Vessels'] + df['Mammalian_Glass_Vessels'] +
                              df['AAV_Man_Vessels'] + df['AAV_Auto_Vessels'])
        
        return df
    
    def _calculate_value_chain(self, df: pd.DataFrame, scenario: Dict[str, Any]) -> pd.DataFrame:
        """Calculate full value chain from manufacturer to end customer with separated components."""
        
        # 1. OUR COSTS (what it costs us to produce/provide)
        # Core hardware costs
        df['Hardware_Our_Cost'] = df['Monthly_New_Carts'] * df['Hardware_Manufacturing_Cost']
        
        # Utility cart costs
        df['Utility_Cart_Our_Cost'] = df['Monthly_New_Carts'] * df['Utility_Cart_Mfg_Cost']
        
        # TCU costs - we pass through at cost
        df['TCU_Our_Cost'] = df['Monthly_New_Carts'] * df['TCU_Mfg_Cost']
        
        # Autofiller unit costs
        df['Autofiller_Unit_Our_Cost'] = df['Monthly_New_Carts'] * df['Autofiller_Unit_Mfg_Cost']
        
        # Installation costs - directly from us
        df['Installation_Our_Cost_Total'] = df['Monthly_New_Carts'] * df['Installation_Our_Cost']
        
        # Software costs
        df['Software_Our_Cost_Total'] = df['Monthly_New_Carts'] * df['Software_Our_Cost'] * df['Software_Revenue_Factor']
        
        # Consumables costs
        df['Vessel_Our_Cost'] = df['Total_Vessels'] * df['Vessel_Manufacturing_Cost']
        df['Autofiller_Pack_Our_Cost'] = df['Total_Vessels'] * df['Autofiller_Pack_Mfg_Cost'] * self.config.consumables.SAFETY_FACTOR
        
        # Service costs (40% of service revenue)
        df['Service_Our_Cost'] = (df['Total_Carts'].shift(1).fillna(0) *
                                df['End_Customer_Hardware_Price'] *
                                self.config.software.SERVICE_CONTRACT_PERCENTAGE / 12 *
                                scenario['service_adoption'] * 0.40)  # 40% cost ratio
        
        # Total our costs
        df['Total_Our_Cost'] = (df['Hardware_Our_Cost'] + df['Utility_Cart_Our_Cost'] + 
                            df['TCU_Our_Cost'] + df['Autofiller_Unit_Our_Cost'] +
                            df['Installation_Our_Cost_Total'] + df['Software_Our_Cost_Total'] + 
                            df['Vessel_Our_Cost'] + df['Autofiller_Pack_Our_Cost'] + 
                            df['Service_Our_Cost'])
        
        # 2. OUR REVENUE (what we receive from the partner)
        # Core hardware system revenue (the main system that includes several components)
        # This includes the core cart, utility cart, TCU and autofiller unit
        df['Hardware_System_Our_Revenue'] = df['Partner_Carts'] * df['Hardware_Partner_Price']
        df['Utility_Cart_Our_Revenue'] = df['Partner_Carts'] * df['Utility_Cart_Partner_Price']
        df['TCU_Our_Revenue'] = df['Partner_Carts'] * df['TCU_Mfg_Cost']  # TCU is pass-through
        df['Autofiller_Unit_Our_Revenue'] = df['Partner_Carts'] * df['Autofiller_Unit_Partner_Price']
        
        # Total hardware system revenue
        df['Total_Hardware_System_Our_Revenue'] = (df['Hardware_System_Our_Revenue'] + 
                                                df['Utility_Cart_Our_Revenue'] + 
                                                df['TCU_Our_Revenue'] + 
                                                df['Autofiller_Unit_Our_Revenue'])
        
        # Services revenue
        # Installation revenue - one-time service per system
        df['Installation_Our_Revenue'] = df['Partner_Carts'] * df['Installation_End_Price']
        
        # Software revenue - direct from end-customers, recurring annual subscription
        df['Software_Our_Revenue'] = df['Partner_Carts'] * df['End_Customer_Software_Price'] * df['Software_Revenue_Factor']
        
        # Support service revenue - recurring annual subscription
        df['Service_Our_Revenue'] = (df['Cumulative_Partner_Carts'].shift(1).fillna(0) *
                                df['End_Customer_Hardware_Price'] *
                                self.config.software.SERVICE_CONTRACT_PERCENTAGE / 12 *
                                scenario['service_adoption'])
        
        # Consumables revenue - these are purchased on an ongoing basis
        carts_ratio_partner = df['Cumulative_Partner_Carts'] / df['Total_Carts'].replace(0, np.nan).fillna(0)
        df['Vessel_Our_Revenue'] = df['Total_Vessels'] * carts_ratio_partner * df['Vessel_Partner_Price']
        df['Autofiller_Pack_Our_Revenue'] = df['Total_Vessels'] * carts_ratio_partner * df['Autofiller_Pack_Partner_Price'] * self.config.consumables.SAFETY_FACTOR
        df['Total_Consumables_Our_Revenue'] = df['Vessel_Our_Revenue'] + df['Autofiller_Pack_Our_Revenue']
        
        # Total our revenue
        df['Total_Our_Revenue'] = (df['Total_Hardware_System_Our_Revenue'] +
                                df['Installation_Our_Revenue'] + 
                                df['Software_Our_Revenue'] + 
                                df['Service_Our_Revenue'] + 
                                df['Total_Consumables_Our_Revenue'])
        
        # 3. END CUSTOMER REVENUE (what customers pay to the partner/market)
        # Hardware system revenue - one-time purchase
        df['Hardware_System_Market_Revenue'] = df['Partner_Carts'] * df['End_Customer_Hardware_Price']
        df['Utility_Cart_Market_Revenue'] = df['Partner_Carts'] * df['Utility_Cart_End_Price']
        df['TCU_Market_Revenue'] = df['Partner_Carts'] * df['TCU_End_Price']
        df['Autofiller_Unit_Market_Revenue'] = df['Partner_Carts'] * df['Autofiller_Unit_End_Price']
        
        # Total hardware system revenue (at market price)
        df['Total_Hardware_System_Market_Revenue'] = (df['Hardware_System_Market_Revenue'] + 
                                                df['Utility_Cart_Market_Revenue'] + 
                                                df['TCU_Market_Revenue'] + 
                                                df['Autofiller_Unit_Market_Revenue'])
        
        # Services market revenue
        df['Installation_Market_Revenue'] = df['Partner_Carts'] * df['Installation_End_Price']
        df['Software_Market_Revenue'] = df['Partner_Carts'] * df['End_Customer_Software_Price'] * df['Software_Revenue_Factor']
        df['Service_Market_Revenue'] = (df['Cumulative_Partner_Carts'].shift(1).fillna(0) *
                                    df['End_Customer_Hardware_Price'] *
                                    self.config.software.SERVICE_CONTRACT_PERCENTAGE / 12 *
                                    scenario['service_adoption'])
        
        # Consumables market revenue
        df['Vessel_Market_Revenue'] = df['Total_Vessels'] * carts_ratio_partner * df['End_Customer_Vessel_Price']
        df['Autofiller_Pack_Market_Revenue'] = df['Total_Vessels'] * carts_ratio_partner * df['End_Customer_Autofiller_Pack_Price'] * self.config.consumables.SAFETY_FACTOR
        df['Total_Consumables_Market_Revenue'] = df['Vessel_Market_Revenue'] + df['Autofiller_Pack_Market_Revenue']
        
        # Total market revenue
        df['Total_Market_Revenue'] = (df['Total_Hardware_System_Market_Revenue'] +
                                    df['Installation_Market_Revenue'] +
                                    df['Software_Market_Revenue'] + 
                                    df['Service_Market_Revenue'] +
                                    df['Total_Consumables_Market_Revenue'])
        
        # 4. PARTNER PROFIT (what the partner makes)
        # Partner profit - they don't get software revenue, TCU is pass-through at cost
        df['Partner_Profit'] = (df['Total_Market_Revenue'] - df['Total_Our_Revenue'] - 
                            df['Software_Market_Revenue'] + df['Software_Our_Revenue'] - 
                            df['TCU_Market_Revenue'] + df['TCU_Our_Revenue'])
        
        return df
    
    def _calculate_profitability(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate profitability metrics with updated revenue structure."""
        # Our profit calculations
        df['Our_Gross_Profit'] = df['Total_Our_Revenue'] - df['Total_Our_Cost']
        
        # Our margin calculations (avoid division by zero)
        our_rev_denom = df['Total_Our_Revenue'].replace(0, np.nan)
        df['Our_Gross_Margin'] = (df['Our_Gross_Profit'] / our_rev_denom).fillna(0)
        
        # Partner margin calculations
        # Partner revenue doesn't include software, adjusted for TCU
        partner_revenue = (df['Total_Market_Revenue'] - df['Software_Market_Revenue'] - 
                        (df['TCU_Market_Revenue'] - df['TCU_Our_Revenue']))
        df['Partner_Margin'] = (df['Partner_Profit'] / partner_revenue.replace(0, np.nan)).fillna(0)
        
        # Component margins for us
        # Hardware system
        hardware_rev = df['Hardware_System_Our_Revenue'].replace(0, np.nan)
        df['Hardware_System_Our_Margin'] = ((df['Hardware_System_Our_Revenue'] - df['Hardware_Our_Cost']) / hardware_rev).fillna(0)
        
        # Utility cart
        utility_rev = df['Utility_Cart_Our_Revenue'].replace(0, np.nan)
        df['Utility_Cart_Our_Margin'] = ((df['Utility_Cart_Our_Revenue'] - df['Utility_Cart_Our_Cost']) / utility_rev).fillna(0)
        
        # TCU - minimal or zero margin as it's pass-through
        tcu_rev = df['TCU_Our_Revenue'].replace(0, np.nan)
        df['TCU_Our_Margin'] = ((df['TCU_Our_Revenue'] - df['TCU_Our_Cost']) / tcu_rev).fillna(0)
        
        # Autofiller unit
        autofiller_unit_rev = df['Autofiller_Unit_Our_Revenue'].replace(0, np.nan)
        df['Autofiller_Unit_Our_Margin'] = ((df['Autofiller_Unit_Our_Revenue'] - df['Autofiller_Unit_Our_Cost']) / autofiller_unit_rev).fillna(0)
        
        # Installation
        installation_rev = df['Installation_Our_Revenue'].replace(0, np.nan)
        df['Installation_Our_Margin'] = ((df['Installation_Our_Revenue'] - df['Installation_Our_Cost_Total']) / installation_rev).fillna(0)
        
        # Software with 100% recognition
        software_rev = df['Software_Our_Revenue'].replace(0, np.nan)
        df['Software_Our_Margin'] = ((df['Software_Our_Revenue'] - df['Software_Our_Cost_Total']) / software_rev).fillna(0)
        
        # Vessels (consumables)
        vessel_rev = df['Vessel_Our_Revenue'].replace(0, np.nan)
        df['Vessel_Our_Margin'] = ((df['Vessel_Our_Revenue'] - df['Vessel_Our_Cost']) / vessel_rev).fillna(0)
        
        # Autofiller packs (consumables)
        autofiller_pack_rev = df['Autofiller_Pack_Our_Revenue'].replace(0, np.nan)
        df['Autofiller_Pack_Our_Margin'] = ((df['Autofiller_Pack_Our_Revenue'] - df['Autofiller_Pack_Our_Cost']) / autofiller_pack_rev).fillna(0)
        
        # Service
        service_rev = df['Service_Our_Revenue'].replace(0, np.nan)
        df['Service_Our_Margin'] = ((df['Service_Our_Revenue'] - df['Service_Our_Cost']) / service_rev).fillna(0)
        
        # Calculate component contribution to total margin
        df['Hardware_System_Contribution'] = df['Total_Hardware_System_Our_Revenue'] / df['Total_Our_Revenue'].replace(0, np.nan)
        df['Software_Contribution'] = df['Software_Our_Revenue'] / df['Total_Our_Revenue'].replace(0, np.nan)
        df['Consumables_Contribution'] = (df['Vessel_Our_Revenue'] + df['Autofiller_Pack_Our_Revenue']) / df['Total_Our_Revenue'].replace(0, np.nan)
        df['Services_Contribution'] = (df['Service_Our_Revenue'] + df['Installation_Our_Revenue']) / df['Total_Our_Revenue'].replace(0, np.nan)
        
        return df
    
    def run_projection(self, scenario: Dict[str, Any], output_path: Optional[str] = None) -> pd.DataFrame:
        """Run the financial projection with the given scenario."""
        # Extract start date from scenario
        start_year = scenario.get('start_year', 2025)
        start_month = scenario.get('start_month', 7)
        projection_years = scenario.get('projection_years', 5)
        
        # Initialize dataframe with relative years
        df = self._initialize_dataframe(start_year, start_month, projection_years)
        
        # Calculate in sequence
        df = self._calculate_cart_sales(df, scenario)
        df = self._calculate_pricing(df, scenario)
        df = self._calculate_consumables(df)
        df = self._calculate_value_chain(df, scenario)
        df = self._calculate_profitability(df)  # Make sure this method is being called
        
        # Export detailed CSV if path is provided
        if output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            df.to_csv(f"{output_path}/financial_projection_{timestamp}.csv", index=False)
            print(f"Financial projection exported to: {output_path}/financial_projection_{timestamp}.csv")
        
        return df