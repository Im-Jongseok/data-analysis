from pathlib import Path

import matplotlib.image as mpimg
import numpy as np
import pandas as pd


class DataAnalyzer:
    """Prepare and analyze a customer-level sample of H&M transactions."""

    def __init__(self, data_path):
        self.data_path = Path(data_path)

    def load_data(self, sample_size=100, random_state=42, chunksize=250_000):
        transaction_path = self.data_path / "transactions_train.csv"
        customer_ids = set()

        with pd.read_csv(
            transaction_path,
            usecols=["customer_id"],
            dtype={"customer_id": "string"},
            chunksize=chunksize,
        ) as chunks:
            for chunk in chunks:
                customer_ids.update(chunk["customer_id"].dropna().unique())

        sample_ids = pd.Series(sorted(customer_ids), dtype="string").sample(
            n=sample_size, random_state=random_state
        )

        with pd.read_csv(
            transaction_path,
            dtype={"customer_id": "string", "article_id": "string"},
            parse_dates=["t_dat"],
            chunksize=chunksize,
        ) as chunks:
            transactions = pd.concat(
                [chunk.loc[chunk["customer_id"].isin(sample_ids)] for chunk in chunks]
            )

        customers = pd.read_csv(
            self.data_path / "customers.csv", dtype={"customer_id": "string"}
        )
        customers = customers.loc[customers["customer_id"].isin(sample_ids)].copy()

        articles = pd.read_csv(
            self.data_path / "articles.csv", dtype={"article_id": "string"}
        )
        article_ids = transactions["article_id"].unique()
        articles = articles.loc[articles["article_id"].isin(article_ids)].copy()

        return transactions, customers, articles

    @staticmethod
    def handle_missing_values(data, column, *, group_col=None, strategy="median"):
        """Fill missing numeric values with a group statistic and an overall fallback."""
        if strategy not in {"median", "mean"}:
            raise ValueError("strategy must be 'median' or 'mean'")

        values = data[column]
        if group_col is not None:
            group_values = data.groupby(group_col)[column].transform(strategy)
            values = values.fillna(group_values)
        return values.fillna(values.agg(strategy))

    @staticmethod
    def detect_outliers(values, threshold=1.5):
        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - threshold * iqr
        upper = q3 + threshold * iqr
        return (values < lower) | (values > upper)

    @staticmethod
    def add_text_features(data):
        return data.assign(product_name_length=data["prod_name"].str.len())

    def image_path(self, article_id):
        return self.data_path / "images" / article_id[:3] / f"{article_id}.jpg"

    def add_image_features(self, articles):
        articles = articles.copy()
        articles["image_mean"] = np.nan
        articles["image_std"] = np.nan

        for index, article_id in articles["article_id"].items():
            path = self.image_path(article_id)
            if path.is_file():
                image = mpimg.imread(path)
                pixels = image.astype(np.float32)
                if np.issubdtype(image.dtype, np.integer):
                    pixels /= np.iinfo(image.dtype).max
                articles.at[index, "image_mean"] = np.mean(pixels)
                articles.at[index, "image_std"] = np.std(pixels)

        return articles

    @staticmethod
    def summarize(data, columns):
        return data[columns].describe()

    @staticmethod
    def calculate_rfm(
        data,
        customer_col="customer_id",
        date_col="t_dat",
        amount_col="price",
        reference_date=None,
    ):
        if reference_date is None:
            reference_date = data[date_col].max()

        rfm = data.groupby(customer_col).agg(
            last_purchase=(date_col, "max"),
            frequency=(date_col, "nunique"),
            monetary=(amount_col, "sum"),
        )
        recency = (pd.Timestamp(reference_date) - rfm.pop("last_purchase")).dt.days
        rfm.insert(0, "recency", recency)
        return rfm
