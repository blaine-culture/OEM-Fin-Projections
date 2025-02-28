from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
from config import Config


class FinancialModel:
    """
    A 'clean' Option B version that:
      - Breaks out the base cart, TCU, utility cart, and autofiller separately (no double counting).
      - Defines all cost/price columns in _calculate_pricing so they're ready for _calculate_value_chain.
      - Omits partial-year software logic (each sold cart gets full $10k software).
      - Adds an optional 'enable_service' flag in the scenario to turn service revenue/cost on/off.
    """

    def __init__(self, config: Config):
        self.config = config

    def _initialize_dataframe(self, start_year: int, start_month: int, projection_years: int) -> pd.DataFrame:
        """
        Build a DataFrame with one row per month from (start_year, start_month) 
        to (start_year+projection_years, start_month-1).
        """
        end_year = start_year + projection_years
        end_month = start_month - 1
        if end_month == 0:
            end_year -= 1
            end_month = 12

        # Generate a row for every (year, month) in range
        years = range(start_year, end_year + 1)
        months = range(1, 13)
        data = [(y, m) for y in years for m in months]
        df = pd.DataFrame(data, columns=['Year', 'Month'])

        # Filter only those rows within our projection window
        start_val = start_year * 12 + start_month
        end_val = end_year * 12 + end_month
        df['Date_Value'] = df['Year'] * 12 + df['Month']
        df = df[(df['Date_Value'] >= start_val) & (df['Date_Value'] <= end_val)]

        # Relative offsets
        df['Months_From_Start'] = df['Date_Value'] - start_val
        df['Relative_Year'] = (df['Months_From_Start'] // 12) + 1
        df['Relative_Month'] = (df['Months_From_Start'] % 12) + 1

        # Quarter info
        df['Quarter'] = ((df['Month'] - 1) // 3) + 1
        df['Month_in_Quarter'] = ((df['Month'] - 1) % 3) + 1

        # For display
        df['Year_Month'] = df.apply(lambda x: f"{x['Year']}-{x['Month']:02d}", axis=1)

        # Fraction of year (used for inflation or cost reduction)
        start_fraction = start_year + (start_month - 1) / 12
        df['Year_Fraction'] = df.apply(
            lambda row: (row['Year'] + (row['Month'] - 1) / 12) - start_fraction,
            axis=1
        )

        return df.reset_index(drop=True)

    def _apply_inflation_and_reduction(self,
                                       initial_value: float,
                                       year_fraction: float,
                                       cost_reduction: float,
                                       apply_inflation: bool,
                                       apply_reduction: bool) -> float:
        """
        Increases value by inflation^(year_fraction) if apply_inflation = True,
        decreases value by cost_reduction * year_fraction if apply_reduction = True (simple linear approach).
        """
        value = initial_value
        if apply_inflation:
            value *= (1 + self.config.financial.INFLATION_RATE) ** year_fraction
        if apply_reduction:
            value *= (1 - cost_reduction * year_fraction)
        return value

    def _calculate_cart_sales(self, df: pd.DataFrame, scenario: Dict[str, Any]) -> pd.DataFrame:
        """
        Distribute cart sales by month for direct vs. partner channels,
        using quarter & month-in-quarter distribution.
        """
        df['Partner_Carts'] = 0
        df['Direct_Carts'] = 0
        df['Total_Carts'] = 0

        partner_sales_by_year = scenario.get('partner_sales_by_year', {})
        direct_sales_by_year = scenario.get('direct_sales_by_year', {})

        quarter_distribution = {1: 0.15, 2: 0.20, 3: 0.25, 4: 0.40}
        month_in_quarter_distribution = {1: 0.20, 2: 0.30, 3: 0.50}

        proj_years = scenario.get('projection_years', 5)
        for rel_year in range(1, proj_years + 1):
            yearly_partner = partner_sales_by_year.get(rel_year, 0)
            yearly_direct = direct_sales_by_year.get(rel_year, 0)

            for quarter in range(1, 5):
                q_pct = quarter_distribution[quarter]
                for miq in range(1, 4):
                    m_pct = month_in_quarter_distribution[miq]
                    monthly_partner = round(yearly_partner * q_pct * m_pct)
                    monthly_direct = round(yearly_direct * q_pct * m_pct)

                    rel_month = (quarter - 1) * 3 + miq
                    mask = (df['Relative_Year'] == rel_year) & (df['Relative_Month'] == rel_month)
                    df.loc[mask, 'Partner_Carts'] = monthly_partner
                    df.loc[mask, 'Direct_Carts'] = monthly_direct

        df['Monthly_New_Carts'] = df['Partner_Carts'] + df['Direct_Carts']
        df['Total_Carts'] = df['Monthly_New_Carts'].cumsum()
        df['Cumulative_Partner_Carts'] = df['Partner_Carts'].cumsum()
        df['Cumulative_Direct_Carts'] = df['Direct_Carts'].cumsum()

        return df

    def _calculate_pricing(self, df: pd.DataFrame, scenario: Dict[str, Any]) -> pd.DataFrame:
        """
        Define all end-customer & partner prices, plus manufacturing costs, in one place.
        That way, they're ready for _calculate_value_chain with no KeyError.
        """
        apply_inflation = scenario.get('apply_inflation', True)
        apply_reduction = scenario.get('apply_reduction', True)
        cost_reduction = scenario.get('cost_reduction', 0.0)

        # 1) Base Hardware (excluding TCU, utility, autofiller)
        df['Base_Hardware_End_Price'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.financial.INITIAL_SELLING_PRICE,  # e.g. 212k for base hardware
                row['Year_Fraction'],
                0,  # no cost reduction for selling price
                apply_inflation,
                False
            ),
            axis=1
        )

        # Apply scenario's year-specific price reduction
        df['Base_Hardware_End_Price_Adjusted'] = df['Base_Hardware_End_Price']
        for rel_year, reduct in scenario.get('selling_price_reduction_by_year', {}).items():
            mask = df['Relative_Year'] == rel_year
            df.loc[mask, 'Base_Hardware_End_Price_Adjusted'] *= (1 - reduct)

        # Base hardware manufacturing cost
        df['Base_Hardware_Manufacturing_Cost'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.cart.COMPONENTS_COST * (1 + self.config.cart.LABOR_COST_PERCENTAGE),
                row['Year_Fraction'],
                cost_reduction,
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )

        # 2) Utility Cart
        df['Utility_Cart_End_Price'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.cart.UTILITY_CART_PRICE,
                row['Year_Fraction'],
                0,
                apply_inflation,
                False
            ),
            axis=1
        )
        df['Utility_Cart_Mfg_Cost'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.cart.UTILITY_CART_COST,
                row['Year_Fraction'],
                cost_reduction,
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )

        # 3) TCU
        df['TCU_End_Price'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.cart.TCU_PRICE,
                row['Year_Fraction'],
                0,
                apply_inflation,
                False
            ),
            axis=1
        )
        df['TCU_Mfg_Cost'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.cart.TCU_COST,
                row['Year_Fraction'],
                cost_reduction,
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )

        # 4) Autofiller
        df['Autofiller_Unit_End_Price'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.cart.AUTOFILLER_PRICE,
                row['Year_Fraction'],
                0,
                apply_inflation,
                False
            ),
            axis=1
        )
        df['Autofiller_Unit_Mfg_Cost'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.cart.AUTOFILLER_COST,
                row['Year_Fraction'],
                cost_reduction,
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )

        # 5) Installation
        df['Installation_End_Price'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.operational.INSTALLATION_PRICE,
                row['Year_Fraction'],
                0,
                apply_inflation,
                False
            ),
            axis=1
        )
        df['Installation_Our_Cost'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.operational.INSTALLATION_COST,
                row['Year_Fraction'],
                cost_reduction,
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )

        # 6) Software (100% margin, no partial year)
        df['End_Customer_Software_Price'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.software.SUBSCRIPTION_PRICE,
                row['Year_Fraction'],
                0,
                apply_inflation,
                False
            ),
            axis=1
        )
        df['Software_Partner_Price'] = 0  # partner doesn't get software

        # 7) Consumables: Vessel
        df['Vessel_Manufacturing_Cost'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.consumables.INITIAL_VESSEL_COST,
                row['Year_Fraction'],
                cost_reduction,
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )
        df['End_Customer_Vessel_Price'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.consumables.INITIAL_VESSEL_PRICE,
                row['Year_Fraction'],
                0,  # typically no cost reduction on list price
                apply_inflation,
                False
            ),
            axis=1
        )

        # 8) Consumables: Autofiller Packs
        df['Autofiller_Pack_Mfg_Cost'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.consumables.INITIAL_AUTOFILLER_PACK_COST,
                row['Year_Fraction'],
                cost_reduction,
                apply_inflation,
                apply_reduction
            ),
            axis=1
        )
        df['End_Customer_Autofiller_Pack_Price'] = df.apply(
            lambda row: self._apply_inflation_and_reduction(
                self.config.consumables.INITIAL_AUTOFILLER_PACK_PRICE,
                row['Year_Fraction'],
                0,
                apply_inflation,
                False
            ),
            axis=1
        )

        # -------- Partner Discounts --------
        # For base hardware, TCU, utility cart, autofiller
        df['Base_Hardware_Partner_Price'] = (
            df['Base_Hardware_End_Price_Adjusted'] * (1 - self.config.operational.PARTNER_HARDWARE_DISCOUNT)
        )
        df['Utility_Cart_Partner_Price'] = (
            df['Utility_Cart_End_Price'] * (1 - self.config.operational.PARTNER_HARDWARE_DISCOUNT)
        )
        # TCU is pass-through, no discount
        df['TCU_Partner_Price'] = df['TCU_End_Price']
        # Autofiller often considered a consumable discount
        df['Autofiller_Unit_Partner_Price'] = (
            df['Autofiller_Unit_End_Price'] * (1 - self.config.operational.PARTNER_CONSUMABLES_DISCOUNT)
        )

        # For vessel & autofiller pack
        df['Vessel_Partner_Price'] = df['End_Customer_Vessel_Price'] * (1 - self.config.operational.PARTNER_CONSUMABLES_DISCOUNT)
        df['Autofiller_Pack_Partner_Price'] = df['End_Customer_Autofiller_Pack_Price'] * (1 - self.config.operational.PARTNER_CONSUMABLES_DISCOUNT)

        return df

    def _calculate_consumables(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate how many total runs, vessels, etc. occur monthly.
        'Total_Vessels' then gets used for cost & revenue in _calculate_value_chain.
        """
        df['Monthly_Runs'] = (
            df['Total_Carts'] * 4 *
            (self.config.process.TOTAL_RUNS_PER_YEAR_PER_CART / 12) *
            self.config.operational.CART_UTILIZATION_PERCENTAGE
        )

        df['Mammalian_Vessels'] = df['Monthly_Runs'] * self.config.process.MAMMALIAN_RUN_PERCENTAGE
        df['Mammalian_Glass_Vessels'] = df['Monthly_Runs'] * self.config.process.MAMMALIAN_GLASS_RUN_PERCENTAGE
        df['AAV_Man_Vessels'] = df['Monthly_Runs'] * self.config.process.AAV_MAN_RUN_PERCENTAGE
        df['AAV_Auto_Vessels'] = df['Monthly_Runs'] * self.config.process.AAV_AUTO_RUN_PERCENTAGE

        df['Total_Vessels'] = (
            df['Mammalian_Vessels']
            + df['Mammalian_Glass_Vessels']
            + df['AAV_Man_Vessels']
            + df['AAV_Auto_Vessels']
        )

        return df

    def _calculate_value_chain(self, df: pd.DataFrame, scenario: Dict[str, Any]) -> pd.DataFrame:
        """
        Summarize:
          1) Our costs for each line item
          2) Our revenue (Partner Price)
          3) Market revenue (End-Customer Price)
          4) Partner profit
          (Service is toggled by scenario['enable_service'])
        """
        enable_service = scenario.get('enable_service', False)
        service_adoption = scenario.get('service_adoption', 0.0)

        # --------------------
        # 1. OUR COSTS
        # --------------------
        # Base hardware
        df['Base_Hardware_Our_Cost'] = (
            df['Monthly_New_Carts'] * df['Base_Hardware_Manufacturing_Cost']
        )

        # TCU pass-through
        df['TCU_Our_Cost'] = df['Partner_Carts'] * df['TCU_Mfg_Cost']

        # Utility cart
        df['Utility_Cart_Our_Cost'] = (
            df['Monthly_New_Carts'] * df['Utility_Cart_Mfg_Cost']
        )

        # Autofiller
        df['Autofiller_Unit_Our_Cost'] = (
            df['Monthly_New_Carts'] * df['Autofiller_Unit_Mfg_Cost']
        )

        # Installation
        df['Installation_Our_Cost_Total'] = (
            df['Monthly_New_Carts'] * df['Installation_Our_Cost']
        )

        # Consumables
        df['Vessel_Our_Cost'] = (
            df['Total_Vessels'] * df['Vessel_Manufacturing_Cost']
        )
        df['Autofiller_Pack_Our_Cost'] = (
            df['Total_Vessels'] 
            * df['Autofiller_Pack_Mfg_Cost']
            * self.config.consumables.SAFETY_FACTOR
        )

        # Service cost
        if enable_service:
            df['Service_Our_Cost'] = (
                df['Total_Carts'].shift(1).fillna(0)
                * df['Base_Hardware_End_Price_Adjusted']
                * self.config.software.SERVICE_CONTRACT_PERCENTAGE
                / 12
                * service_adoption
                * self.config.operational.SERVICE_COST_RATIO
            )
        else:
            df['Service_Our_Cost'] = 0

        # Sum total cost
        df['Total_Our_Cost'] = (
            df['Base_Hardware_Our_Cost']
            + df['TCU_Our_Cost']
            + df['Utility_Cart_Our_Cost']
            + df['Autofiller_Unit_Our_Cost']
            + df['Installation_Our_Cost_Total']
            + df['Vessel_Our_Cost']
            + df['Autofiller_Pack_Our_Cost']
            + df['Service_Our_Cost']
        )

        # --------------------
        # 2. OUR REVENUE
        # --------------------
        # Base hardware
        df['Base_Hardware_Our_Revenue'] = (
            df['Partner_Carts'] * df['Base_Hardware_Partner_Price']
        )
        # TCU pass-through
        df['TCU_Our_Revenue'] = (
            df['Partner_Carts'] * df['TCU_Mfg_Cost']
        )
        # Utility cart
        df['Utility_Cart_Our_Revenue'] = (
            df['Partner_Carts'] * df['Utility_Cart_Partner_Price']
        )
        # Autofiller
        df['Autofiller_Unit_Our_Revenue'] = (
            df['Partner_Carts'] * df['Autofiller_Unit_Partner_Price']
        )

        # Summed hardware revenue
        df['Total_Hardware_System_Our_Revenue'] = (
            df['Base_Hardware_Our_Revenue']
            + df['TCU_Our_Revenue']
            + df['Utility_Cart_Our_Revenue']
            + df['Autofiller_Unit_Our_Revenue']
        )

        # Installation
        df['Installation_Our_Revenue'] = (
            df['Partner_Carts'] * df['Installation_End_Price']
        )

        # Software
        df['Software_Our_Revenue'] = (
            df['Partner_Carts'] * df['End_Customer_Software_Price']
        )

        # Service
        if enable_service:
            df['Service_Our_Revenue'] = (
                df['Cumulative_Partner_Carts'].shift(1).fillna(0)
                * df['Base_Hardware_End_Price_Adjusted']
                * self.config.software.SERVICE_CONTRACT_PERCENTAGE
                / 12
                * service_adoption
            )
        else:
            df['Service_Our_Revenue'] = 0

        # Consumables
        ratio_partner = (
            df['Cumulative_Partner_Carts'] /
            df['Total_Carts'].replace(0, np.nan).fillna(0)
        )
        df['Vessel_Our_Revenue'] = (
            df['Total_Vessels']
            * ratio_partner
            * df['Vessel_Partner_Price']
        )
        df['Autofiller_Pack_Our_Revenue'] = (
            df['Total_Vessels']
            * ratio_partner
            * df['Autofiller_Pack_Partner_Price']
            * self.config.consumables.SAFETY_FACTOR
        )
        df['Total_Consumables_Our_Revenue'] = (
            df['Vessel_Our_Revenue'] + df['Autofiller_Pack_Our_Revenue']
        )

        df['Total_Our_Revenue'] = (
            df['Total_Hardware_System_Our_Revenue']
            + df['Installation_Our_Revenue']
            + df['Software_Our_Revenue']
            + df['Service_Our_Revenue']
            + df['Total_Consumables_Our_Revenue']
        )

        # --------------------
        # 3. MARKET REVENUE
        # --------------------
        df['Base_Hardware_Market_Revenue'] = (
            df['Partner_Carts'] * df['Base_Hardware_End_Price_Adjusted']
        )
        df['TCU_Market_Revenue'] = (
            df['Partner_Carts'] * df['TCU_End_Price']
        )
        df['Utility_Cart_Market_Revenue'] = (
            df['Partner_Carts'] * df['Utility_Cart_End_Price']
        )
        df['Autofiller_Unit_Market_Revenue'] = (
            df['Partner_Carts'] * df['Autofiller_Unit_End_Price']
        )
        df['Total_Hardware_System_Market_Revenue'] = (
            df['Base_Hardware_Market_Revenue']
            + df['TCU_Market_Revenue']
            + df['Utility_Cart_Market_Revenue']
            + df['Autofiller_Unit_Market_Revenue']
        )

        df['Installation_Market_Revenue'] = (
            df['Partner_Carts'] * df['Installation_End_Price']
        )
        df['Software_Market_Revenue'] = (
            df['Partner_Carts'] * df['End_Customer_Software_Price']
        )

        if enable_service:
            df['Service_Market_Revenue'] = (
                df['Cumulative_Partner_Carts'].shift(1).fillna(0)
                * df['Base_Hardware_End_Price_Adjusted']
                * self.config.software.SERVICE_CONTRACT_PERCENTAGE
                / 12
                * service_adoption
            )
        else:
            df['Service_Market_Revenue'] = 0

        df['Vessel_Market_Revenue'] = (
            df['Total_Vessels']
            * ratio_partner
            * df['End_Customer_Vessel_Price']
        )
        df['Autofiller_Pack_Market_Revenue'] = (
            df['Total_Vessels']
            * ratio_partner
            * df['End_Customer_Autofiller_Pack_Price']
            * self.config.consumables.SAFETY_FACTOR
        )
        df['Total_Consumables_Market_Revenue'] = (
            df['Vessel_Market_Revenue']
            + df['Autofiller_Pack_Market_Revenue']
        )

        df['Total_Market_Revenue'] = (
            df['Total_Hardware_System_Market_Revenue']
            + df['Installation_Market_Revenue']
            + df['Software_Market_Revenue']
            + df['Service_Market_Revenue']
            + df['Total_Consumables_Market_Revenue']
        )

        # --------------------
        # 4. PARTNER PROFIT
        # --------------------
        df['Partner_Profit'] = (
            df['Total_Market_Revenue']
            - df['Total_Our_Revenue']
            # remove software from partner top-line
            - df['Software_Market_Revenue']
            + df['Software_Our_Revenue']
            # remove TCU pass-through
            - df['TCU_Market_Revenue']
            + df['TCU_Our_Revenue']
        )

        return df

    def _calculate_profitability(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate final margins: 
          - Our_Gross_Margin
          - Partner_Margin (excludes software + TCU pass-through)
        """
        df['Our_Gross_Profit'] = df['Total_Our_Revenue'] - df['Total_Our_Cost']
        df['Our_Gross_Margin'] = (
            df['Our_Gross_Profit'] / df['Total_Our_Revenue'].replace(0, np.nan)
        ).fillna(0)

        # Partner margin excludes software revenue & TCU pass-through 
        partner_revenue = (
            df['Total_Market_Revenue']
            - df['Software_Market_Revenue']
            - (df['TCU_Market_Revenue'] - df['TCU_Our_Revenue'])
        )
        df['Partner_Margin'] = (
            df['Partner_Profit'] / partner_revenue.replace(0, np.nan)
        ).fillna(0)

        return df

    def run_projection(self, scenario: Dict[str, Any], output_path: Optional[str] = None) -> pd.DataFrame:
        """
        The main pipeline for generating the monthly/annual projection:
          1) Build the DF
          2) Calculate cart sales
          3) Define all prices/costs
          4) Consumables usage
          5) Build value chain
          6) Calculate profitability
          7) Optional export
        """
        start_year = scenario.get('start_year', 2025)
        start_month = scenario.get('start_month', 7)
        projection_years = scenario.get('projection_years', 5)

        df = self._initialize_dataframe(start_year, start_month, projection_years)
        df = self._calculate_cart_sales(df, scenario)
        df = self._calculate_pricing(df, scenario)
        df = self._calculate_consumables(df)
        df = self._calculate_value_chain(df, scenario)
        df = self._calculate_profitability(df)

        if output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = f"{output_path}/financial_projection_{timestamp}.csv"
            df.to_csv(out_file, index=False)
            print(f"Financial projection exported to: {out_file}")

        return df
