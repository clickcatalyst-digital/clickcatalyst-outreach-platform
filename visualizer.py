# visualizer.py
# Input:  competitor_analysis_data for a given Target_CIN
# Output: Clean minimal scatter plot PNG saved to /output/plots/ AND in-memory buffer for email

import sqlite3
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend — safe for batch/server use
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import io
import os
from datetime import date

DB_PATH    = 'company_master_data.db'
PLOTS_DIR  = 'output/plots'

# --- Color palette (clean minimal) ---
COLOR_TARGET      = '#1a1a2e'   # Deep navy — the star
COLOR_ADS         = '#e63946'   # Red — competitor confirmed running ads
COLOR_UNKNOWN     = '#adb5bd'   # Neutral grey — unknown pixel status
COLOR_NO_ADS      = '#dee2e6'   # Light grey — confirmed no ads
COLOR_BENCHMARK   = '#6c757d'   # Mid grey dashed line
FONT_FAMILY       = 'DejaVu Sans'


def _ensure_plots_dir():
    os.makedirs(PLOTS_DIR, exist_ok=True)


def _get_scatter_data(target_cin, db_path=DB_PATH):
    """Pulls competitor_analysis_data for one target CIN."""
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("""
        SELECT
            Competitor_Name,
            Capital,
            Age_In_Days,
            Has_Pixel,
            Is_Target_Lead,
            Industry_Benchmark_Avg
        FROM competitor_analysis_data
        WHERE Target_CIN = ?
        ORDER BY Is_Target_Lead DESC
    """, conn, params=(target_cin,))
    conn.close()
    return df


def _dot_color(row):
    """Maps pixel status + role to a plot color."""
    if row['Is_Target_Lead'] == 1:
        return COLOR_TARGET
    if row['Has_Pixel'] is None or pd.isna(row['Has_Pixel']):
        return COLOR_UNKNOWN
    if int(row['Has_Pixel']) == 1:
        return COLOR_ADS
    return COLOR_NO_ADS


def generate_scatter_plot(target_cin, target_name, db_path=DB_PATH):
    """
    Generates a clean minimal scatter plot for one lead.
    Saves PNG to disk AND returns an in-memory BytesIO buffer for email attachment.

    Returns: (filepath: str, buffer: BytesIO)
    """
    df = _get_scatter_data(target_cin, db_path)

    if df.empty:
        print(f"   [Visualizer] No scatter data found for {target_cin} — skipping.")
        return None, None

    benchmark = df['Industry_Benchmark_Avg'].iloc[0]

    # --- Split target row from competitor rows ---
    target_row  = df[df['Is_Target_Lead'] == 1].iloc[0]
    competitors = df[df['Is_Target_Lead'] == 0].copy()

    # --- Figure setup ---
    fig, ax = plt.subplots(figsize=(9, 5.5))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    # Subtle grid
    ax.grid(True, which='major', linestyle='--', linewidth=0.4, color='#e0e0e0', zorder=0)
    ax.set_axisbelow(True)

    # --- Plot competitor dots ---
    for _, row in competitors.iterrows():
        color = _dot_color(row)
        ax.scatter(
            row['Age_In_Days'],
            row['Capital'],
            color=color,
            s=60,
            alpha=0.85,
            edgecolors='white',
            linewidths=0.5,
            zorder=2
        )

    # --- Plot target as a bold star ---
    ax.scatter(
        target_row['Age_In_Days'],
        target_row['Capital'],
        color=COLOR_TARGET,
        s=280,
        marker='*',
        edgecolors='white',
        linewidths=0.8,
        zorder=4,
        label='_nolegend_'
    )

    # Target label
    ax.annotate(
        f"  {target_name}",
        xy=(target_row['Age_In_Days'], target_row['Capital']),
        fontsize=8,
        fontweight='bold',
        color=COLOR_TARGET,
        va='center',
        zorder=5
    )

    # --- Benchmark line ---
    if benchmark:
        ax.axhline(
            y=benchmark,
            color=COLOR_BENCHMARK,
            linestyle='--',
            linewidth=1.0,
            alpha=0.7,
            zorder=1
        )
        ax.text(
            ax.get_xlim()[1] if ax.get_xlim()[1] != 0 else df['Age_In_Days'].max(),
            benchmark,
            f'  Cohort Avg ₹{benchmark:,.0f}',
            va='bottom',
            ha='right',
            fontsize=7,
            color=COLOR_BENCHMARK,
            style='italic'
        )

    # --- Axes ---
    ax.set_xlabel('Company Age (Days)', fontsize=9, color='#444444', labelpad=8)
    ax.set_ylabel('Paid-up Capital (₹)', fontsize=9, color='#444444', labelpad=8)
    ax.tick_params(axis='both', labelsize=8, color='#cccccc')

    for spine in ax.spines.values():
        spine.set_edgecolor('#e0e0e0')

    # Y-axis formatted as currency
    ax.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda x, _: f'₹{x/1e5:.1f}L')
    )

    # --- Legend ---
    legend_elements = [
        Line2D([0], [0], marker='*', color='w', markerfacecolor=COLOR_TARGET,
               markersize=12, label='You (Target Lead)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=COLOR_ADS,
               markersize=7, label='Peer — Ads Confirmed'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=COLOR_UNKNOWN,
               markersize=7, label='Peer — Status Unknown'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=COLOR_NO_ADS,
               markersize=7, label='Peer — No Ads Detected'),
        Line2D([0], [0], linestyle='--', color=COLOR_BENCHMARK,
               linewidth=1, label='Cohort Avg Capital'),
    ]
    ax.legend(
        handles=legend_elements,
        fontsize=7.5,
        frameon=True,
        framealpha=0.9,
        edgecolor='#e0e0e0',
        loc='upper left'
    )

    # --- Title ---
    ax.set_title(
        f'Competitive Landscape — {target_name}',
        fontsize=11,
        fontweight='bold',
        color='#1a1a2e',
        pad=14
    )

    # Subtle footer
    fig.text(
        0.99, 0.01,
        f'Generated by ClickCatalyst · {date.today().strftime("%d %b %Y")}',
        ha='right', va='bottom',
        fontsize=6.5, color='#aaaaaa', style='italic'
    )

    plt.tight_layout()

    # --- Save to disk ---
    _ensure_plots_dir()
    filename = f"{target_cin}_{date.today().isoformat()}.png"
    filepath = os.path.join(PLOTS_DIR, filename)
    plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')

    # --- Also write to in-memory buffer for email ---
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    buffer.seek(0)

    plt.close(fig)

    print(f"   [Visualizer] Plot saved → {filepath}")
    return filepath, buffer