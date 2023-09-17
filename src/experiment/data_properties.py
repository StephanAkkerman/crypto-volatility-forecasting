from collections import Counter

import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.formula.api import ols
from scipy.stats import kruskal, mannwhitneyu

import config
from experiment.rmse import read_rmse_csv
from data_analysis.stochasticity import calc_hurst


def high_auto_cor(test_type: str):
    # Make an analysis of the data
    df = pd.read_csv(f"{config.statistics_dir}/{test_type}_log_returns.csv")

    # Grouping the DataFrame by 'Coin' and 'Time Frame' and counting the occurrences of "Autocorrelated"
    grouped_df = (
        df.groupby(["Coin", "Time Frame", "Result"]).size().reset_index(name="Count")
    )

    # Create a pivot table to show counts of "Autocorrelated" and "Not Autocorrelated" side by side
    pivot_df = grouped_df.pivot_table(
        index=["Coin", "Time Frame"], columns="Result", values="Count", fill_value=0
    ).reset_index()

    # Calculate a column to determine if predominantly "Autocorrelated"
    pivot_df["Predominantly"] = np.where(
        pivot_df["Autocorrelated"] > 49, "Autocorrelated", "Not Autocorrelated"
    )

    return pivot_df[["Coin", "Time Frame", "Predominantly"]]


def merge_rmse(df):
    # Add RMSE data to the DataFrame
    rmse_dfs = []
    for time_frame in config.timeframes:
        rmse_df = read_rmse_csv(
            pred=config.log_returns_pred, time_frame=time_frame, avg=True
        )

        # Add timeframe to it
        rmse_df["Time Frame"] = time_frame

        # Name index coin
        rmse_df["Coin"] = rmse_df.index

        rmse_dfs.append(rmse_df)

    # Concatenate the DataFrames
    rmse_df = pd.concat(rmse_dfs, axis=0, ignore_index=True)

    # Add RMSE data to the DataFrame
    df = pd.merge(df, rmse_df, how="inner", on=["Coin", "Time Frame"])

    return df


def auto_correlation():
    # Find the cryptocurrencies that show autocorrelation on the log returns
    ljung = high_auto_cor("Ljung-Box")
    breusch = high_auto_cor("Breusch-Godfrey")

    # Find the overlap between the two DataFrames and determine the final 'Result'
    overlap = pd.merge(
        ljung,
        breusch,
        how="outer",
        on=["Coin", "Time Frame"],
        suffixes=("_ljung", "_breusch"),
    )
    overlap["Result"] = np.where(
        (overlap["Predominantly_ljung"] == "Autocorrelated")
        & (overlap["Predominantly_breusch"] == "Autocorrelated"),
        "Autocorrelated",
        "Not Autocorrelated",
    )

    overlap = overlap[["Coin", "Time Frame", "Result"]]

    overlap = merge_rmse(overlap)

    anova(overlap)


def anova(df):
    # Perform the ANOVA test
    for model in config.all_models:  # Assuming Result is the last column
        formula = (
            f'{model} ~ C(Result) + C(Q("Time Frame")) + C(Result):C(Q("Time Frame"))'
        )
        lm = ols(formula, df).fit()
        table = sm.stats.anova_lm(lm, typ=2)
        print(f"ANOVA table for {model}:\n", table)


def find_majority(row):
    # Count the frequency of each unique result in the row
    counter = Counter(row)
    # Find the most common result
    most_common_result, freq = counter.most_common(1)[0]
    return most_common_result


def trend():
    # trend_tests(as_csv=True)
    df = pd.read_csv(f"{config.statistics_dir}/trend_results_log_returns.csv")

    # Finding rows where all test columns have the same value
    # result_df = df[df.iloc[:, 2:].apply(lambda row: len(row.unique()) == 1, axis=1)]

    # Apply the function across the rows
    df["Result"] = df.apply(find_majority, axis=1)

    # Drop the columns that are not needed
    df = df[["Coin", "Time Frame", "Result"]]

    # Change Results to trend if its increasing or decreasing
    df["Result"] = df["Result"].str.replace("increasing", "trend")
    df["Result"] = df["Result"].str.replace("decreasing", "trend")

    # Add RMSE data to the DataFrame
    df = merge_rmse(df)

    # Save test results
    results = {}

    for model in config.all_models:
        groups = [df[df["Result"] == result][model] for result in df["Result"].unique()]
        results[model] = mannwhitneyu(*groups)

    print(results)


def seasonality():
    # Get seasonality data
    # seasonal_strength_test(log_returns=True)

    # Read seasonality data
    df = pd.read_csv(f"{config.statistics_dir}/stl_seasonality_log_returns.csv")

    # Add RMSE data to the DataFrame
    df = merge_rmse(df)

    results = {}

    for forecasting_model in config.all_models:
        # Prepare the independent variable 'Seasonal Strength' and add a constant term for the intercept
        X = sm.add_constant(df["Seasonal Strength"])

        # Prepare the dependent variable. This is for RandomForest. Repeat for other models.
        y = df[forecasting_model]

        # Perform linear regression
        model = sm.OLS(y, X).fit()

        # Convert the summary results to a DataFrame
        results_df = pd.DataFrame(model.summary2().tables[1])

        # Access the p-value for "Seasonal Strength"
        p_value_seasonal_strength = results_df.loc["Seasonal Strength", "P>|t|"]

        results[forecasting_model] = p_value_seasonal_strength

    print(results)


def heteroskedasticity():
    # cond_het()

    uncon_het()


def uncon_het():
    df = pd.read_csv(
        f"{config.statistics_dir}/unconditional_heteroskedasticity_log_returns.csv"
    )
    # Find rows where 'Breusch-Pagan' and 'Goldfeld-Quandt' have the same result
    # same_result_df = df[df['Breusch-Pagan'] == df['Goldfeld-Quandt']]

    # First test using breusch-pagan
    df = merge_rmse(df)

    breusch_results = {}
    for model in config.all_models:
        groups = [
            df[df["Breusch-Pagan"] == result][model]
            for result in df["Breusch-Pagan"].unique()
        ]
        breusch_results[model] = mannwhitneyu(*groups)

    goldfeld_results = {}
    for model in config.all_models:
        groups = [
            df[df["Goldfeld-Quandt"] == result][model]
            for result in df["Goldfeld-Quandt"].unique()
        ]
        goldfeld_results[model] = mannwhitneyu(*groups)

    print(breusch_results)
    print(goldfeld_results)


def cond_het():
    df = pd.read_csv(f"{config.statistics_dir}/cond_heteroskedasticity_log_returns.csv")

    # Add RMSE data to the DataFrame
    df = merge_rmse(df)

    # Save test results
    results = {}

    for model in config.all_models:
        groups = [df[df["result"] == result][model] for result in df["result"].unique()]
        results[model] = mannwhitneyu(*groups)

    print(results)


def correlation():
    pass


def stochasticity():
    # calc_hurst()

    df = pd.read_csv(f"{config.statistics_dir}/hurst_log_returns.csv")

    print(df["Result"].value_counts())

    # Add RMSE data to the DataFrame
    df = merge_rmse(df)

    # Save test results
    results = {}

    for model in config.all_models:
        groups = [df[df["Result"] == result][model] for result in df["Result"].unique()]
        results[model] = mannwhitneyu(*groups)

    print(results)