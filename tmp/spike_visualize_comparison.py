"""
Visual comparison: Raw counts vs. Normalized rates

This demonstrates why normalization matters.
"""

import pandas as pd

def compare_rankings():
    print("="*80)
    print("WHY NORMALIZATION MATTERS: RANKING COMPARISON")
    print("="*80)

    # Load data
    df = pd.read_parquet('tmp/events_with_population_r5.parquet')
    df = df[df['population'] >= 100].copy()  # Filter low-population outliers

    # Top 10 by raw count
    top_count = df.nlargest(10, 'event_count')[['h3_cell', 'event_count', 'population', 'rate_per_10000']].reset_index(drop=True)
    top_count.index += 1

    # Top 10 by normalized rate
    top_rate = df.nlargest(10, 'rate_per_10000')[['h3_cell', 'event_count', 'population', 'rate_per_10000']].reset_index(drop=True)
    top_rate.index += 1

    print("\n" + "-"*80)
    print("TOP 10 BY RAW EVENT COUNT")
    print("-"*80)
    print("\nRank | H3 Cell             | Events | Population | Rate/10k")
    print("-" * 70)
    for idx, row in top_count.iterrows():
        print(f"{idx:4d} | {row['h3_cell']:15s} | {row['event_count']:6,d} | {row['population']:10,.0f} | {row['rate_per_10000']:8.1f}")

    print("\n" + "-"*80)
    print("TOP 10 BY NORMALIZED RATE (per 10,000 residents)")
    print("-"*80)
    print("\nRank | H3 Cell             | Events | Population | Rate/10k")
    print("-" * 70)
    for idx, row in top_rate.iterrows():
        print(f"{idx:4d} | {row['h3_cell']:15s} | {row['event_count']:6,d} | {row['population']:10,.0f} | {row['rate_per_10000']:8.1f}")

    # Analysis
    print("\n" + "="*80)
    print("KEY INSIGHTS")
    print("="*80)

    # Cells in both lists
    both_lists = set(top_count['h3_cell']) & set(top_rate['h3_cell'])
    print(f"\nCells appearing in BOTH top-10 lists: {len(both_lists)}")

    if len(both_lists) > 0:
        print("These areas have both high absolute counts AND high per-capita rates:")
        for cell in both_lists:
            row_count = top_count[top_count['h3_cell'] == cell].iloc[0]
            rank_count = top_count[top_count['h3_cell'] == cell].index[0]
            rank_rate = top_rate[top_rate['h3_cell'] == cell].index[0]
            print(f"  - {cell}: Rank #{rank_count} by count, #{rank_rate} by rate")

    # Cells only in rate list (high intensity, lower absolute)
    only_rate = set(top_rate['h3_cell']) - set(top_count['h3_cell'])
    print(f"\nCells in top-10 by RATE but not COUNT: {len(only_rate)}")
    print("These are smaller areas with disproportionately high crime intensity:")
    for cell in only_rate:
        row = top_rate[top_rate['h3_cell'] == cell].iloc[0]
        print(f"  - {cell}: {row['event_count']:,} events / {row['population']:,.0f} pop = {row['rate_per_10000']:,.0f} per 10k")

    # Cells only in count list (big cities, not necessarily highest rate)
    only_count = set(top_count['h3_cell']) - set(top_rate['h3_cell'])
    print(f"\nCells in top-10 by COUNT but not RATE: {len(only_count)}")
    print("These are large cities with many events but moderate per-capita rates:")
    for cell in only_count:
        row = top_count[top_count['h3_cell'] == cell].iloc[0]
        print(f"  - {cell}: {row['event_count']:,} events / {row['population']:,.0f} pop = {row['rate_per_10000']:,.1f} per 10k")

    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    print("\n📊 Raw counts answer: 'Where do most crimes occur?'")
    print("   → Cities like Stockholm, Malmö (large population centers)")
    print("\n📈 Normalized rates answer: 'Where are crimes most frequent relative to population?'")
    print("   → Often smaller urban centers, commercial districts, transit hubs")
    print("\n💡 BOTH perspectives are valuable for different analyses:")
    print("   • Resource allocation → Use raw counts (where to deploy most officers)")
    print("   • Risk assessment → Use normalized rates (where residents face highest risk)")
    print("   • Policy analysis → Compare both to understand patterns")
    print("\n✅ Recommendation: Provide BOTH views with easy toggle in UI")

if __name__ == "__main__":
    compare_rankings()
