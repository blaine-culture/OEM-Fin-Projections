from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
from config import Config

class FinancialModel:
    """Simplified financial model that incorporates OEM partnership."""
    
    def __init__(self, config: Config):
        self.config = config
        
    def _initialize_dataframe(self) -> pd.DataFrame:
        """Initialize DataFrame with monthly granularity for projection."""
        years = range(2025, 2030)
        months = range(1, 13)
        data = [(year, month) for year in years for month in months]
        df = pd.DataFrame(data, columns=['Year', 'Month'])
        df['Quarter'] = ((df['Month'] - 1) // 3) + 1
        df['Month_in_Quarter'] = ((df['Month'] - 1) % 3) + 1
        df['Year_Month'] = df.apply(lambda x: f"{x['Year']}-{x['Month']:02d}", axis=1)
        # Remove Q1 2025 as per requirements
        df = df[~((df['Year'] == 2025) & (df['Quarter'] == 1))]
        return df.reset_index(drop=True)
    
    def _apply_inflation_and_reduction(self, initial_value: float, year_fraction: float, cost_reduction: float) -> float:
        """Apply inflation and cost reduction over time."""
        inflation_factor = (1 + self.config.financial.INFLATION_RATE) ** year_fraction
        reduction_factor = 1 - (cost_reduction * year_fraction)
        return initial_value * inflation_factor * reduction_factor
    
    def _calculate_year_fraction(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate year fraction for inflation adjustments."""
        df['Year_Fraction'] = (df['Year'] - 2025) + (df['Month'] - 1) / 12
        return df
    
    def _calculate_cart_sales(self, df: pd.DataFrame, scenario: Dict[str, Any]) -> pd.DataFrame:
        """Calculate cart sales for direct and partner channels based on scenario."""
        # Initialize cart columns
        df['Total_Carts'] = 0
        df['Direct_Carts'] = 0
        df['Partner_Carts'] = 0
        
        # Calculate total carts and split between direct and partner based on scenario
        for year in range(2025, 2030):
            # Get the total carts for the year from scenario
            yearly_partner_carts = scenario['partner_sales_per_year'].get(year, 0)
            
            # Distribution by quarter and by month in quarter
            quarter_distribution = {1: 0.15, 2: 0.20, 3: 0.25, 4: 0.40}
            month_in_quarter_distribution = {1: 0.20, 2: 0.30, 3: 0.50}
            
            # For 2025, adjust distribution since Q1 is removed
            if year == 2025:
                total_remaining = 1 - quarter_distribution[1]
                quarter_distribution = {
                    2: quarter_distribution[2] / total_remaining,
                    3: quarter_distribution[3] / total_remaining,
                    4: quarter_distribution[4] / total_remaining
                }
            
            # Distribute carts by quarter and month
            for quarter, quarter_pct in quarter_distribution.items():
                for month_in_quarter, month_pct in month_in_quarter_distribution.items():
                    month = (quarter - 1) * 3 + month_in_quarter
                    
                    # Skip Q1 2025
                    if year == 2025 and quarter == 1:
                        continue
                    
                    # Calculate partner carts for this month
                    monthly_partner_carts = round(yearly_partner_carts * quarter_pct * month_pct)
                    
                    # Apply to the DataFrame
                    mask = (df['Year'] == year) & (df['Month'] == month)
                    df.loc[mask, 'Partner_Carts'] = monthly_partner_carts
        
        # Calculate direct carts based on the partnership percentage
        direct_sales_pct = self.config.operational.DIRECT_SALES_PERCENTAGE
        # Initially this is 0%, so direct carts will be 0
        df['Direct_Carts'] = 0
        
        # Calculate cumulative values
        df['Total_Carts'] = df['Direct_Carts'].cumsum() + df['Partner_Carts'].cumsum()
        df['Cumulative_Direct_Carts'] = df['Direct_Carts'].cumsum() 
        df['Cumulative_Partner_Carts'] = df['Partner_Carts'].cumsum()
        
        return df
    
    def _calculate_pricing(self, df: pd.DataFrame, scenario: Dict[str, Any]) -> pd.DataFrame:
        """Calculate basic pricing information."""
        df = self._calculate_year_fraction(df)
        
        # Calculate base selling price with inflation adjustments
        df['Base_Selling_Price'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.financial.INITIAL_SELLING_PRICE, 
                x['Year_Fraction'], 
                0
            ),
            axis=1
        )
        
        # Apply selling price reduction from scenario
        df['Hardware_Selling_Price'] = df['Base_Selling_Price']
        for year, reduction in scenario['selling_price_reduction'].items():
            df.loc[df['Year'] == year, 'Hardware_Selling_Price'] *= (1 - reduction)
        
        # Calculate internal costs
        df['Cart_Internal_Cost'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.cart.COMPONENTS_COST * (1 + self.config.cart.LABOR_COST_PERCENTAGE),
                x['Year_Fraction'],
                scenario['cost_reduction']
            ),
            axis=1
        )
        
        # Calculate utility cart and TCU costs
        df['Utility_Cart_TCU_Cost'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                (self.config.cart.UTILITY_CART_ASSEMBLY + self.config.cart.TCU_COST) *
                (1 + self.config.cart.LABOR_COST_PERCENTAGE),
                x['Year_Fraction'],
                scenario['cost_reduction']
            ),
            axis=1
        )
        
        df['Total_Hardware_Internal_Cost'] = df['Cart_Internal_Cost'] + df['Utility_Cart_TCU_Cost']
        
        # Software pricing
        df['Software_Selling_Price'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.software.SUBSCRIPTION_PRICE, 
                x['Year_Fraction'], 
                0
            ),
            axis=1
        )
        df['Software_Internal_Cost'] = df['Software_Selling_Price'] * 0.20
        df['Software_Year_Fraction'] = (13 - df['Month']) / 12
        df['Software_Revenue_Factor'] = df.apply(lambda x: x['Software_Year_Fraction'] if x['Month'] > 1 else 1, axis=1)
        
        # Consumables pricing
        df['Vessel_Selling_Price'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.consumables.INITIAL_VESSEL_PRICE, 
                x['Year_Fraction'], 
                0
            ),
            axis=1
        )
        df['Vessel_Internal_Cost'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.consumables.INITIAL_VESSEL_COST, 
                x['Year_Fraction'], 
                scenario['cost_reduction']
            ),
            axis=1
        )
        
        # Autofiller pack pricing
        df['Autofiller_Pack_Selling_Price'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.consumables.INITIAL_AUTOFILLER_PACK_PRICE, 
                x['Year_Fraction'], 
                0
            ),
            axis=1
        )
        df['Autofiller_Pack_Internal_Cost'] = df.apply(
            lambda x: self._apply_inflation_and_reduction(
                self.config.consumables.INITIAL_AUTOFILLER_PACK_COST, 
                x['Year_Fraction'], 
                scenario['cost_reduction']
            ),
            axis=1
        )
        
        # Calculate partner discounted prices
        df['Partner_Hardware_Selling_Price'] = df['Hardware_Selling_Price'] * (1 - self.config.operational.PARTNER_HARDWARE_DISCOUNT)
        df['Partner_Vessel_Selling_Price'] = df['Vessel_Selling_Price'] * (1 - self.config.operational.PARTNER_CONSUMABLES_DISCOUNT)
        df['Partner_Autofiller_Pack_Selling_Price'] = df['Autofiller_Pack_Selling_Price'] * (1 - self.config.operational.PARTNER_CONSUMABLES_DISCOUNT)
        
        return df
    
    def _calculate_consumables(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate consumables usage and distribution."""
        # Calculate monthly runs
        df['Monthly_Runs'] = ((df['Direct_Carts'] + df['Partner_Carts']).cumsum() * 4 *
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
    
    def _calculate_revenue(self, df: pd.DataFrame, scenario: Dict[str, Any]) -> pd.DataFrame:
        """Calculate revenue streams with OEM partnership model."""
        # Direct hardware revenue
        df['Direct_Hardware_Revenue'] = df['Direct_Carts'] * df['Hardware_Selling_Price']
        
        # Partner hardware revenue (discounted)
        df['Partner_Hardware_Revenue'] = df['Partner_Carts'] * df['Partner_Hardware_Selling_Price']
        
        # Software revenue (no discount for partners)
        df['Direct_Software_Revenue'] = df['Direct_Carts'] * df['Software_Selling_Price'] * df['Software_Revenue_Factor']
        df['Partner_Software_Revenue'] = df['Partner_Carts'] * df['Software_Selling_Price'] * df['Software_Revenue_Factor']
        
        # Consumables revenue
        # First, calculate base vessel revenue
        df['Direct_Mammalian_Revenue'] = df['Mammalian_Vessels'] * df['Cumulative_Direct_Carts'] / df['Total_Carts'].replace(0, np.nan).fillna(0) * df['Vessel_Selling_Price']
        df['Direct_Mammalian_Glass_Revenue'] = df['Mammalian_Glass_Vessels'] * df['Cumulative_Direct_Carts'] / df['Total_Carts'].replace(0, np.nan).fillna(0) * df['Vessel_Selling_Price']
        df['Direct_AAV_Man_Revenue'] = df['AAV_Man_Vessels'] * df['Cumulative_Direct_Carts'] / df['Total_Carts'].replace(0, np.nan).fillna(0) * df['Vessel_Selling_Price']
        df['Direct_AAV_Auto_Revenue'] = df['AAV_Auto_Vessels'] * df['Cumulative_Direct_Carts'] / df['Total_Carts'].replace(0, np.nan).fillna(0) * df['Vessel_Selling_Price']
        
        # Partner vessel revenue (with discount)
        df['Partner_Mammalian_Revenue'] = df['Mammalian_Vessels'] * df['Cumulative_Partner_Carts'] / df['Total_Carts'].replace(0, np.nan).fillna(0) * df['Partner_Vessel_Selling_Price']
        df['Partner_Mammalian_Glass_Revenue'] = df['Mammalian_Glass_Vessels'] * df['Cumulative_Partner_Carts'] / df['Total_Carts'].replace(0, np.nan).fillna(0) * df['Partner_Vessel_Selling_Price']
        df['Partner_AAV_Man_Revenue'] = df['AAV_Man_Vessels'] * df['Cumulative_Partner_Carts'] / df['Total_Carts'].replace(0, np.nan).fillna(0) * df['Partner_Vessel_Selling_Price']
        df['Partner_AAV_Auto_Revenue'] = df['AAV_Auto_Vessels'] * df['Cumulative_Partner_Carts'] / df['Total_Carts'].replace(0, np.nan).fillna(0) * df['Partner_Vessel_Selling_Price']
        
        # Total consumables revenue
        df['Direct_Consumables_Revenue'] = (df['Direct_Mammalian_Revenue'] + df['Direct_Mammalian_Glass_Revenue'] +
                                          df['Direct_AAV_Man_Revenue'] + df['Direct_AAV_Auto_Revenue'])
        
        df['Partner_Consumables_Revenue'] = (df['Partner_Mammalian_Revenue'] + df['Partner_Mammalian_Glass_Revenue'] +
                                           df['Partner_AAV_Man_Revenue'] + df['Partner_AAV_Auto_Revenue'])
        
        # Autofiller revenue
        df['Direct_Autofiller_Revenue'] = (df['Total_Vessels'] * df['Cumulative_Direct_Carts'] / df['Total_Carts'].replace(0, np.nan).fillna(0) * 
                                         df['Autofiller_Pack_Selling_Price'] * self.config.consumables.SAFETY_FACTOR)
        
        df['Partner_Autofiller_Revenue'] = (df['Total_Vessels'] * df['Cumulative_Partner_Carts'] / df['Total_Carts'].replace(0, np.nan).fillna(0) * 
                                          df['Partner_Autofiller_Pack_Selling_Price'] * self.config.consumables.SAFETY_FACTOR)
        
        # Service revenue
        df['Direct_Service_Revenue'] = (df['Cumulative_Direct_Carts'].shift(1).fillna(0) *
                                      df['Hardware_Selling_Price'] *
                                      self.config.software.SERVICE_CONTRACT_PERCENTAGE / 12 *
                                      scenario['service_adoption'])
        
        df['Partner_Service_Revenue'] = (df['Cumulative_Partner_Carts'].shift(1).fillna(0) *
                                       df['Hardware_Selling_Price'] *
                                       self.config.software.SERVICE_CONTRACT_PERCENTAGE / 12 *
                                       scenario['service_adoption'])
        
        # Additional service revenue if specified in scenario
        if 'additional_revenue' in scenario and scenario['additional_revenue'] > 0:
            df['Direct_Additional_Service_Revenue'] = df['Direct_Service_Revenue'] * scenario['additional_revenue']
            df['Partner_Additional_Service_Revenue'] = df['Partner_Service_Revenue'] * scenario['additional_revenue']
            df['Direct_Service_Revenue'] += df['Direct_Additional_Service_Revenue']
            df['Partner_Service_Revenue'] += df['Partner_Additional_Service_Revenue']
        
        # Total revenue calculations
        df['Hardware_Revenue'] = df['Direct_Hardware_Revenue'] + df['Partner_Hardware_Revenue']
        df['Software_Revenue'] = df['Direct_Software_Revenue'] + df['Partner_Software_Revenue']
        df['Consumables_Revenue'] = df['Direct_Consumables_Revenue'] + df['Partner_Consumables_Revenue']
        df['Autofiller_Revenue'] = df['Direct_Autofiller_Revenue'] + df['Partner_Autofiller_Revenue']
        df['Service_Revenue'] = df['Direct_Service_Revenue'] + df['Partner_Service_Revenue']
        
        # Calculate total revenue
        df['Total_Revenue'] = (df['Hardware_Revenue'] + df['Software_Revenue'] + 
                              df['Consumables_Revenue'] + df['Autofiller_Revenue'] + 
                              df['Service_Revenue'])
        
        return df
    
    def _calculate_costs(self, df: pd.DataFrame, scenario: Dict[str, Any]) -> pd.DataFrame:
        """Calculate all cost components."""
        # Hardware costs
        df['Hardware_Cost'] = (df['Direct_Carts'] + df['Partner_Carts']) * df['Total_Hardware_Internal_Cost']
        
        # Software costs
        df['Software_Cost'] = (df['Direct_Carts'] + df['Partner_Carts']) * df['Software_Internal_Cost'] * df['Software_Revenue_Factor']
        
        # Consumables costs
        df['Mammalian_Cost'] = df['Mammalian_Vessels'] * df['Vessel_Internal_Cost']
        df['Mammalian_Glass_Cost'] = df['Mammalian_Glass_Vessels'] * df['Vessel_Internal_Cost']
        df['AAV_Man_Cost'] = df['AAV_Man_Vessels'] * df['Vessel_Internal_Cost']
        df['AAV_Auto_Cost'] = df['AAV_Auto_Vessels'] * df['Vessel_Internal_Cost']
        df['Consumables_Cost'] = (df['Mammalian_Cost'] + df['Mammalian_Glass_Cost'] +
                                 df['AAV_Man_Cost'] + df['AAV_Auto_Cost'])
        
        # Autofiller costs
        df['Autofiller_Cost'] = df['Total_Vessels'] * df['Autofiller_Pack_Internal_Cost'] * self.config.consumables.SAFETY_FACTOR
        
        # Service costs (40% of service revenue)
        df['Service_Cost'] = df['Service_Revenue'] * 0.40
        
        # Warranty costs
        df['Warranty_Cost'] = df['Hardware_Revenue'] * self.config.warranty.PERCENTAGE * self.config.warranty.COST_PERCENTAGE
        
        # Installation costs (50% of installation price)
        df['Installation_Cost'] = (df['Direct_Carts'] + df['Partner_Carts']) * self.config.operational.INSTALLATION_PRICE * 0.50
        
        # Operating costs
        df['RD_Cost'] = df['Total_Revenue'] * self.config.financial.RD_PERCENTAGE / 12
        df['Marketing_Cost'] = df['Total_Revenue'] * self.config.financial.MARKETING_PERCENTAGE / 12
        df['Sales_Cost'] = df['Total_Revenue'] * self.config.financial.SALES_PERCENTAGE / 12
        df['Facility_Cost'] = df['Total_Revenue'] * self.config.financial.FACILITY_COST_PERCENTAGE / 12
        df['Total_Operating_Cost'] = df['RD_Cost'] + df['Marketing_Cost'] + df['Sales_Cost'] + df['Facility_Cost']
        
        # Total costs
        df['Total_Direct_Cost'] = (df['Hardware_Cost'] + df['Software_Cost'] + df['Consumables_Cost'] +
                                  df['Service_Cost'] + df['Warranty_Cost'] + df['Installation_Cost'] +
                                  df['Autofiller_Cost'])
        df['Total_Cost'] = df['Total_Direct_Cost'] + df['Total_Operating_Cost']
        
        return df
    
    def _calculate_profitability(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate profitability metrics."""
        # Profit calculations
        df['Gross_Profit'] = df['Total_Revenue'] - df['Total_Cost']
        df['Operating_Profit'] = df['Gross_Profit'] - df['Total_Operating_Cost']
        
        # Margin calculations (avoid division by zero)
        rev_denom = df['Total_Revenue'].replace(0, np.nan)
        df['Gross_Margin'] = (df['Gross_Profit'] / rev_denom).fillna(0)
        df['Operating_Margin'] = (df['Operating_Profit'] / rev_denom).fillna(0)
        
        # Component margins
        hardware_rev = df['Hardware_Revenue'].replace(0, np.nan)
        df['Hardware_Margin'] = ((df['Hardware_Revenue'] - df['Hardware_Cost']) / hardware_rev).fillna(0)
        
        software_rev = df['Software_Revenue'].replace(0, np.nan)
        df['Software_Margin'] = ((df['Software_Revenue'] - df['Software_Cost']) / software_rev).fillna(0)
        
        consumables_rev = df['Consumables_Revenue'].replace(0, np.nan)
        df['Consumables_Margin'] = ((df['Consumables_Revenue'] - df['Consumables_Cost']) / consumables_rev).fillna(0)
        
        service_rev = df['Service_Revenue'].replace(0, np.nan)
        df['Service_Margin'] = ((df['Service_Revenue'] - df['Service_Cost']) / service_rev).fillna(0)
        
        return df
    
    def run_projection(self, scenario: Dict[str, Any], output_path: Optional[str] = None) -> pd.DataFrame:
        """Run the financial projection with the given scenario."""
        df = self._initialize_dataframe()
        
        # Calculate in sequence
        df = self._calculate_cart_sales(df, scenario)
        df = self._calculate_pricing(df, scenario)
        df = self._calculate_consumables(df)
        df = self._calculate_revenue(df, scenario)
        df = self._calculate_costs(df, scenario)
        df = self._calculate_profitability(df)
        
        # Export detailed CSV if path is provided
        if output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            df.to_csv(f"{output_path}/financial_projection_{timestamp}.csv", index=False)
            print(f"Financial projection exported to: {output_path}/financial_projection_{timestamp}.csv")
        
        return df