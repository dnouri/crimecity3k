"""
Join crime events with population data to calculate normalized rates.

This script demonstrates:
1. Loading crime events from events.parquet
2. Converting events to H3 cells
3. Joining with population data
4. Calculating normalized crime rates (events per capita)
5. Comparing raw counts vs. normalized rates
"""

import duckdb
import pandas as pd
import h3

def load_events_and_convert_to_h3(resolution=5):
    """
    Load events from parquet and convert to H3 cells.

    Args:
        resolution: H3 resolution to use

    Returns:
        DataFrame with events aggregated by H3 cell
    """
    print(f"\nLoading events and converting to H3 resolution {resolution}...")

    conn = duckdb.connect()

    # Load events and convert to H3 in a single query
    # Note: DuckDB doesn't have H3 built-in, so we'll load to pandas first
    events = conn.execute("""
        SELECT
            latitude,
            longitude,
            name,
            datetime,
            location_name
        FROM read_parquet('data/events.parquet')
    """).df()

    print(f"Loaded {len(events):,} events")

    # Convert to H3
    print("Converting to H3 cells...")
    events['h3_cell'] = events.apply(
        lambda row: h3.latlng_to_cell(row['latitude'], row['longitude'], resolution),
        axis=1
    )

    # Aggregate by H3 cell
    events_agg = events.groupby('h3_cell').agg({
        'name': 'count',  # Count of events
        'latitude': 'first',  # Keep a sample location
        'longitude': 'first'
    }).reset_index()

    events_agg.rename(columns={'name': 'event_count'}, inplace=True)

    print(f"Aggregated to {len(events_agg):,} unique H3 cells")
    print(f"Mean events per cell: {events_agg['event_count'].mean():.1f}")
    print(f"Max events in a cell: {events_agg['event_count'].max()}")

    return events_agg

def join_with_population(events_h3, population_h3):
    """
    Join events with population data.

    Args:
        events_h3: DataFrame with event counts by H3 cell
        population_h3: DataFrame with population by H3 cell

    Returns:
        DataFrame with events, population, and normalized rates
    """
    print("\nJoining events with population...")

    # Left join to keep all event cells
    joined = events_h3.merge(
        population_h3,
        on='h3_cell',
        how='left'
    )

    # Fill missing population with 0 (cells with events but no population)
    joined['population'] = joined['population'].fillna(0)

    print(f"Total cells after join: {len(joined):,}")
    print(f"Cells with population data: {(joined['population'] > 0).sum():,}")
    print(f"Cells without population data: {(joined['population'] == 0).sum():,}")

    # Calculate normalized rates
    # Events per 1000 residents (avoid division by zero)
    joined['rate_per_1000'] = joined.apply(
        lambda row: (row['event_count'] / row['population'] * 1000)
        if row['population'] > 0 else 0,
        axis=1
    )

    # Events per 10000 residents for better readability
    joined['rate_per_10000'] = joined.apply(
        lambda row: (row['event_count'] / row['population'] * 10000)
        if row['population'] > 0 else 0,
        axis=1
    )

    return joined

def analyze_results(df):
    """Analyze joined results."""
    print("\n" + "="*80)
    print("ANALYSIS: RAW COUNTS VS. NORMALIZED RATES")
    print("="*80)

    # Filter cells with population
    df_pop = df[df['population'] > 0].copy()

    print(f"\nCells with both events and population: {len(df_pop):,}")

    # Top 10 by raw event count
    print("\n" + "-"*80)
    print("TOP 10 CELLS BY RAW EVENT COUNT:")
    print("-"*80)
    top_count = df_pop.nlargest(10, 'event_count')
    for idx, row in top_count.iterrows():
        lat, lon = h3.cell_to_latlng(row['h3_cell'])
        print(f"  {row['h3_cell']}")
        print(f"    Events: {row['event_count']:,}")
        print(f"    Population: {row['population']:,.0f}")
        print(f"    Rate per 10,000: {row['rate_per_10000']:.1f}")
        print(f"    Location: {lat:.4f}, {lon:.4f}")
        print()

    # Top 10 by normalized rate (minimum population threshold)
    print("-"*80)
    print("TOP 10 CELLS BY NORMALIZED RATE (events per 10,000 residents):")
    print("(Minimum population: 100 to avoid small sample bias)")
    print("-"*80)
    df_min_pop = df_pop[df_pop['population'] >= 100].copy()
    top_rate = df_min_pop.nlargest(10, 'rate_per_10000')
    for idx, row in top_rate.iterrows():
        lat, lon = h3.cell_to_latlng(row['h3_cell'])
        print(f"  {row['h3_cell']}")
        print(f"    Events: {row['event_count']:,}")
        print(f"    Population: {row['population']:,.0f}")
        print(f"    Rate per 10,000: {row['rate_per_10000']:.1f}")
        print(f"    Location: {lat:.4f}, {lon:.4f}")
        print()

    # Summary statistics
    print("-"*80)
    print("SUMMARY STATISTICS:")
    print("-"*80)
    print(f"\nTotal events: {df_pop['event_count'].sum():,}")
    print(f"Total population: {df_pop['population'].sum():,.0f}")
    print(f"Overall rate per 10,000: {(df_pop['event_count'].sum() / df_pop['population'].sum() * 10000):.1f}")

    print("\nEvent count distribution:")
    print(df_pop['event_count'].describe())

    print("\nNormalized rate distribution (per 10,000):")
    print(df_min_pop['rate_per_10000'].describe())

def save_results(df, resolution):
    """Save joined results for visualization."""
    output_file = f'tmp/events_with_population_r{resolution}.parquet'
    df.to_parquet(output_file)
    print(f"\n" + "="*80)
    print(f"Results saved to: {output_file}")
    print("="*80)

    # Also save a CSV sample for easy inspection
    csv_file = f'tmp/events_with_population_r{resolution}_sample.csv'
    df_sample = df[df['population'] > 0].nlargest(100, 'event_count')
    df_sample.to_csv(csv_file, index=False)
    print(f"Sample CSV saved to: {csv_file}")

def test_multiple_resolutions():
    """Test joining at different resolutions."""
    print("="*80)
    print("TESTING MULTIPLE H3 RESOLUTIONS")
    print("="*80)

    resolutions = [5, 6]

    for res in resolutions:
        print(f"\n{'='*80}")
        print(f"RESOLUTION {res}")
        print(f"{'='*80}")

        # Load events
        events_h3 = load_events_and_convert_to_h3(resolution=res)

        # Load population
        pop_file = f'tmp/population_h3_r{res}.parquet'
        population_h3 = pd.read_parquet(pop_file)
        print(f"Loaded population data: {len(population_h3):,} cells")

        # Join
        joined = join_with_population(events_h3, population_h3)

        # Analyze
        analyze_results(joined)

        # Save
        save_results(joined, res)

def main():
    print("="*80)
    print("JOIN CRIME EVENTS WITH POPULATION DATA")
    print("="*80)

    test_multiple_resolutions()

    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    print("\nPopulation normalization is feasible and provides valuable insights:")
    print("  ✓ Raw counts show where most events occur (usually cities)")
    print("  ✓ Normalized rates show where events are most frequent relative to population")
    print("  ✓ Both perspectives are valuable for different analyses")
    print("\nRecommendation: Include both metrics in visualization")
    print("  - Default view: Raw event counts")
    print("  - Toggle option: Normalized rates (events per 10,000 residents)")
    print("  - Filter: Minimum population threshold to avoid noise")

if __name__ == "__main__":
    main()
