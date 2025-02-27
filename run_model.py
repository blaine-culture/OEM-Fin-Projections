import os
from pathlib import Path
from financial_model import FinancialModel
from config import Config

def main():
    # Initialize configuration
    config = Config()
    
    # Define scenario parameters with OEM partnership model
    scenario = {
        'cost_reduction': 0,
        'service_adoption': 0.80,
        'additional_revenue': 0,
        'selling_price_reduction': {2025: 0, 2026: 0, 2027: 0, 2028: 0, 2029: 0},
        # Define total sales per year (initially all partner sales)
        'partner_sales_per_year': {2025: 4, 2026: 10, 2027: 40, 2028: 52, 2029: 64},
        'direct_sales_per_year': {2025: 0, 2026: 0, 2027: 0, 2028: 0, 2029: 0}
    }
    
    # Create projection
    model = FinancialModel(config)
    output_dir = str(Path.home() / "Downloads")
    df = model.run_projection(scenario, output_dir)
    
    # Display key metrics
    print("\nKey Metrics Summary:")
    print("-" * 50)
    annual_summary = df.groupby('Year').agg({
        'Total_Revenue': 'sum',
        'Total_Cost': 'sum',
        'Gross_Profit': 'sum',
        'Direct_Carts': 'sum',
        'Partner_Carts': 'sum'
    }).reset_index()
    
    annual_summary['Gross_Margin'] = annual_summary['Gross_Profit'] / annual_summary['Total_Revenue']
    
    print(annual_summary[['Year', 'Total_Revenue', 'Gross_Profit', 'Gross_Margin', 'Direct_Carts', 'Partner_Carts']])

if __name__ == "__main__":
    main()