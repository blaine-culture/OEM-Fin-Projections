import os
from pathlib import Path
import pandas as pd
from financial_model import FinancialModel
from config import Config

def main():
    # Initialize configuration
    config = Config()
    
    # Define scenario parameters with OEM partnership model
    scenario = {
        # Start date for the projection
        'start_year': 2025,
        'start_month': 7,
        'projection_years': 5,
        
        # Core parameters
        'cost_reduction': 0,
        'service_adoption': 0.80,
        
        # Inflation and reduction control flags
        'apply_inflation': False,  # Set to False to disable inflation
        'apply_reduction': False,  # Set to False to disable cost reduction
        
        # Price reductions by relative year
        'selling_price_reduction_by_year': {
            1: 0,    # Year 1 (Jul 2025 - Jun 2026)
            2: 0,    # Year 2 (Jul 2026 - Jun 2027)
            3: 0,    # Year 3 (Jul 2027 - Jun 2028)
            4: 0,    # Year 4 (Jul 2028 - Jun 2029)
            5: 0     # Year 5 (Jul 2029 - Jun 2030)
        },
        
        # Updated sales projections by relative year
        'partner_sales_by_year': {
            1: 30,   # Year 1 (Jul 2025 - Jun 2026) 
            2: 71,   # Year 2 (Jul 2026 - Jun 2027)
            3: 115,  # Year 3 (Jul 2027 - Jun 2028)
            4: 176,  # Year 4 (Jul 2028 - Jun 2029)
            5: 261   # Year 5 (Jul 2029 - Jun 2030)
        },
        
        # Direct sales projections by relative year (initially all zero)
        'direct_sales_by_year': {
            1: 0,    # Year 1 (Jul 2025 - Jun 2026)
            2: 0,    # Year 2 (Jul 2026 - Jun 2027)
            3: 0,    # Year 3 (Jul 2027 - Jun 2028)
            4: 0,    # Year 4 (Jul 2028 - Jun 2029)
            5: 0     # Year 5 (Jul 2029 - Jun 2030)
        }
    }
    
    # Create projection
    model = FinancialModel(config)
    output_dir = str(Path.home() / "Downloads")
    df = model.run_projection(scenario, output_dir)
    
    # Display key metrics by relative year for the full value chain
    print("\nValue Chain Summary by Relative Year:")
    print("-" * 80)
    
    # Create a value chain summary
    value_chain_summary = df.groupby('Relative_Year').agg({
        'Total_Our_Cost': 'sum',          # Using correct column name
        'Total_Our_Revenue': 'sum',        
        'Total_Market_Revenue': 'sum',     
        'Our_Gross_Profit': 'sum',         
        'Partner_Profit': 'sum',           
        'Partner_Carts': 'sum'             
    }).reset_index()
    
    # Calculate additional metrics
    value_chain_summary['Our_Gross_Margin'] = value_chain_summary['Our_Gross_Profit'] / value_chain_summary['Total_Our_Revenue']
    value_chain_summary['Partner_Margin'] = value_chain_summary['Partner_Profit'] / (value_chain_summary['Total_Market_Revenue'] - value_chain_summary['Total_Our_Revenue'])
    
    # Add date range for clearer reporting
    value_chain_summary['Period'] = value_chain_summary['Relative_Year'].apply(
        lambda rel_year: f"Year {rel_year}: {scenario['start_month']}/{scenario['start_year'] + rel_year - 1}-{scenario['start_month']-1 or 12}/{scenario['start_year'] + rel_year if scenario['start_month'] > 1 else scenario['start_year'] + rel_year - 1 + 1}"
    )
    
    # Format numbers for easier reading
    pd.options.display.float_format = '${:,.0f}'.format
    
    # Display the summary
    print(value_chain_summary[['Period', 'Partner_Carts', 'Total_Our_Cost', 'Total_Our_Revenue', 
                             'Our_Gross_Margin', 'Partner_Profit', 'Partner_Margin', 'Total_Market_Revenue']]
          .rename(columns={
              'Total_Our_Cost': 'Our Cost',
              'Total_Our_Revenue': 'Our Revenue', 
              'Our_Gross_Margin': 'Our Margin',
              'Partner_Profit': 'Partner Profit',
              'Partner_Margin': 'Partner Margin',
              'Total_Market_Revenue': 'Market Revenue',
              'Partner_Carts': 'Units Sold'
          }))
    
    # Show component margins
    print("\nComponent Margin Verification:")
    print("-" * 80)
    
    # Only include margin columns that are guaranteed to exist
    try:
        margin_columns = [col for col in df.columns if 'Margin' in col and col != 'Partner_Margin']
        component_margins = df.groupby('Relative_Year')[margin_columns].mean().reset_index()
        
        # Format as percentages
        for col in component_margins.columns:
            if col != 'Relative_Year':
                component_margins[col] = component_margins[col].map('{:.1%}'.format)
        
        print(component_margins)
    except Exception as e:
        print(f"Unable to display component margins: {e}")
    
    # Show revenue by component category
    print("\nRevenue by Component Category:")
    print("-" * 80)

    try:
        revenue_categories = df.groupby('Relative_Year').agg({
            'Total_Hardware_System_Our_Revenue': 'sum',
            'Software_Our_Revenue': 'sum',
            'Total_Consumables_Our_Revenue': 'sum',
            'Service_Our_Revenue': 'sum',
            'Installation_Our_Revenue': 'sum',
            'Partner_Carts': 'sum'
        }).reset_index()
        
        # Calculate percentages of total revenue
        for year_idx in revenue_categories.index:
            total = revenue_categories.loc[year_idx, 'Total_Hardware_System_Our_Revenue'] + \
                revenue_categories.loc[year_idx, 'Software_Our_Revenue'] + \
                revenue_categories.loc[year_idx, 'Total_Consumables_Our_Revenue'] + \
                revenue_categories.loc[year_idx, 'Service_Our_Revenue'] + \
                revenue_categories.loc[year_idx, 'Installation_Our_Revenue']
            
            revenue_categories.loc[year_idx, 'Hardware_Pct'] = revenue_categories.loc[year_idx, 'Total_Hardware_System_Our_Revenue'] / total
            revenue_categories.loc[year_idx, 'Software_Pct'] = revenue_categories.loc[year_idx, 'Software_Our_Revenue'] / total
            revenue_categories.loc[year_idx, 'Consumables_Pct'] = revenue_categories.loc[year_idx, 'Total_Consumables_Our_Revenue'] / total
            revenue_categories.loc[year_idx, 'Service_Pct'] = revenue_categories.loc[year_idx, 'Service_Our_Revenue'] / total
            revenue_categories.loc[year_idx, 'Installation_Pct'] = revenue_categories.loc[year_idx, 'Installation_Our_Revenue'] / total
        
        # Format revenue as currency and percentages
        for col in revenue_categories.columns:
            if 'Revenue' in col:
                revenue_categories[col] = revenue_categories[col].map('${:,.0f}'.format)
            elif 'Pct' in col:
                revenue_categories[col] = revenue_categories[col].map('{:.1%}'.format)
        
        print(revenue_categories[['Relative_Year', 'Partner_Carts', 
                                'Total_Hardware_System_Our_Revenue', 'Hardware_Pct',
                                'Software_Our_Revenue', 'Software_Pct',
                                'Total_Consumables_Our_Revenue', 'Consumables_Pct',
                                'Service_Our_Revenue', 'Service_Pct',
                                'Installation_Our_Revenue', 'Installation_Pct']])
    except Exception as e:
        print(f"Unable to display revenue by category: {e}")

if __name__ == "__main__":
    main()