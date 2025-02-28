import os
from pathlib import Path
import pandas as pd

# Import the new FinancialModel class and the updated Config class
from financial_model import FinancialModel
from config import Config

def main():
    # 1. Initialize configuration
    config = Config()
    
    # 2. Define scenario parameters
    scenario = {
        'start_year': 2025,
        'start_month': 7,
        'projection_years': 5,
        'cost_reduction': 0,
        'service_adoption': 0.80,
        'apply_inflation': False,
        'apply_reduction': False,
        'enable_service': False,  # By default, no service revenue/cost

        'selling_price_reduction_by_year': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        'partner_sales_by_year': {1: 30, 2: 71, 3: 135, 4: 176, 5: 261},
        'direct_sales_by_year': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    }

    
    # 3. Run the projection
    model = FinancialModel(config)

    # Example output directory (adjust to your preference)
    output_dir = str(Path.home() / "Downloads")
    df = model.run_projection(scenario, output_dir)

    # 4. Display key metrics by relative year for the full value chain
    print("\nValue Chain Summary by Relative Year:")
    print("-" * 80)

    # Simple aggregation by year
    value_chain_summary = df.groupby('Relative_Year').agg({
        'Total_Our_Cost': 'sum',
        'Total_Our_Revenue': 'sum',
        'Total_Market_Revenue': 'sum',
        'Our_Gross_Profit': 'sum',
        'Partner_Profit': 'sum',
        'Partner_Carts': 'sum'
    }).reset_index()

    # Calculate margins
    value_chain_summary['Our_Gross_Margin'] = (
        value_chain_summary['Our_Gross_Profit'] / value_chain_summary['Total_Our_Revenue']
    )
    value_chain_summary['Partner_Margin'] = (
        value_chain_summary['Partner_Profit'] 
        / (value_chain_summary['Total_Market_Revenue'] - value_chain_summary['Total_Our_Revenue'])
    )

    # Add date range text for clarity
    value_chain_summary['Period'] = value_chain_summary['Relative_Year'].apply(
        lambda rel_year: (
            f"Year {rel_year}: "
            f"{scenario['start_month']}/{scenario['start_year'] + rel_year - 1}"
            f"-{scenario['start_month']-1 or 12}/{scenario['start_year'] + rel_year if scenario['start_month'] > 1 else scenario['start_year'] + rel_year - 1 + 1}"
        )
    )

    pd.options.display.float_format = '${:,.0f}'.format
    
    # Print the summary
    print(
        value_chain_summary[
            ['Period', 'Partner_Carts', 'Total_Our_Cost', 'Total_Our_Revenue',
             'Our_Gross_Margin', 'Partner_Profit', 'Partner_Margin', 'Total_Market_Revenue']
        ].rename(columns={
            'Total_Our_Cost': 'Our Cost',
            'Total_Our_Revenue': 'Our Revenue',
            'Our_Gross_Margin': 'Our Margin',
            'Partner_Profit': 'Partner Profit',
            'Partner_Margin': 'Partner Margin',
            'Total_Market_Revenue': 'Market Revenue',
            'Partner_Carts': 'Units Sold'
        })
    )

    # 5. Show component margins (hardware, TCU, warranty, etc.)
    print("\nComponent Margin Verification:")
    print("-" * 80)
    try:
        # Find columns with "Margin" in their name (except 'Partner_Margin' which we already displayed)
        margin_columns = [col for col in df.columns if 'Margin' in col and col != 'Partner_Margin']
        component_margins = df.groupby('Relative_Year')[margin_columns].mean().reset_index()

        # Format margins as percentages
        for col in component_margins.columns:
            if col != 'Relative_Year':
                component_margins[col] = component_margins[col].map('{:.1%}'.format)

        print(component_margins)
    except Exception as e:
        print(f"Unable to display component margins: {e}")

    # 6. Show revenue by component category
    print("\nRevenue by Component Category:")
    print("-" * 80)
    try:
        revenue_categories = df.groupby('Relative_Year').agg({
            'Total_Hardware_System_Our_Revenue': 'sum',
            'Software_Our_Revenue': 'sum',
            'Total_Consumables_Our_Revenue': 'sum',
            'Service_Our_Revenue': 'sum',
            'Installation_Our_Revenue': 'sum',
            'Warranty_Our_Revenue': 'sum',     # If you want to see total warranty recognized
            'Partner_Carts': 'sum'
        }).reset_index()

        for year_idx in revenue_categories.index:
            total_rev = (
                revenue_categories.loc[year_idx, 'Total_Hardware_System_Our_Revenue']
                + revenue_categories.loc[year_idx, 'Software_Our_Revenue']
                + revenue_categories.loc[year_idx, 'Total_Consumables_Our_Revenue']
                + revenue_categories.loc[year_idx, 'Service_Our_Revenue']
                + revenue_categories.loc[year_idx, 'Installation_Our_Revenue']
                + revenue_categories.loc[year_idx, 'Warranty_Our_Revenue']
            )

            # Calculate percentages
            if total_rev != 0:
                revenue_categories.loc[year_idx, 'Hardware_Pct'] = (
                    revenue_categories.loc[year_idx, 'Total_Hardware_System_Our_Revenue'] / total_rev
                )
                revenue_categories.loc[year_idx, 'Software_Pct'] = (
                    revenue_categories.loc[year_idx, 'Software_Our_Revenue'] / total_rev
                )
                revenue_categories.loc[year_idx, 'Consumables_Pct'] = (
                    revenue_categories.loc[year_idx, 'Total_Consumables_Our_Revenue'] / total_rev
                )
                revenue_categories.loc[year_idx, 'Service_Pct'] = (
                    revenue_categories.loc[year_idx, 'Service_Our_Revenue'] / total_rev
                )
                revenue_categories.loc[year_idx, 'Installation_Pct'] = (
                    revenue_categories.loc[year_idx, 'Installation_Our_Revenue'] / total_rev
                )
                revenue_categories.loc[year_idx, 'Warranty_Pct'] = (
                    revenue_categories.loc[year_idx, 'Warranty_Our_Revenue'] / total_rev
                )
            else:
                # if total_rev == 0
                for col in ['Hardware_Pct', 'Software_Pct', 'Consumables_Pct', 
                            'Service_Pct', 'Installation_Pct', 'Warranty_Pct']:
                    revenue_categories.loc[year_idx, col] = 0.0

        # Format currency and percentage columns
        for col in revenue_categories.columns:
            if 'Revenue' in col:
                revenue_categories[col] = revenue_categories[col].map('${:,.0f}'.format)
            elif 'Pct' in col:
                revenue_categories[col] = revenue_categories[col].map('{:.1%}'.format)

        print(
            revenue_categories[
                ['Relative_Year', 'Partner_Carts',
                 'Total_Hardware_System_Our_Revenue', 'Hardware_Pct',
                 'Software_Our_Revenue', 'Software_Pct',
                 'Total_Consumables_Our_Revenue', 'Consumables_Pct',
                 'Service_Our_Revenue', 'Service_Pct',
                 'Installation_Our_Revenue', 'Installation_Pct',
                 'Warranty_Our_Revenue', 'Warranty_Pct']
            ]
        )
    except Exception as e:
        print(f"Unable to display revenue by category: {e}")


if __name__ == "__main__":
    main()
