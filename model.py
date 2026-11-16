"""LightGBM sınıflandırıcı + walk-forward (ileriye yürüyen) eğitim.
Model her zaman sadece geçmiş günlerle eğitilir, hiç görmediği günlerde test edilir."""
import os
import pickle

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from features import FEATURES

PARAMS = dict(
    objective="binary", learning_rate=0.03, num_leaves=15, min_child_samples=200,
    feature_fraction=0.7, bagging_fraction=0.7, bagging_freq=1, lambda_l2=5.0,
    n_estimators=300, verbose=-1,
)


def train(df: pd.DataFrame) -> lgb.LGBMClassifier:
    d = df.dropna(subset=FEATURES + ["label"])
    m = lgb.LGBMClassifier(**PARAMS)
    m.fit(d[FEATURES], d["label"])
    return m


def walk_forward(df: pd.DataFrame, train_days=40, test_days=5) -> pd.DataFrame:
    """Kaydırmalı pencere: 40 gün eğit -> sonraki 5 günü tahmin et -> kaydır."""
    days = np.array(sorted(set(df.index.get_level_values("timestamp").date)))
    dates = df.index.get_level_values("timestamp").date
    preds = []
    aucs = []
    for start in range(train_days, len(days), test_days):
        tr_days = set(days[start - train_days:start])
        te_days = set(days[start:start + test_days])
        tr = df[np.isin(dates, list(tr_days))]
        te = df[np.isin(dates, list(te_days))].dropna(subset=FEATURES)
        if len(te) == 0:
            continue
        m = train(tr)
        p = pd.Series(m.predict_proba(te[FEATURES])[:, 1], index=te.index, name="prob")
        preds.append(p)
        lab = te["label"].dropna()
        if lab.nunique() == 2:
            aucs.append(roc_auc_score(lab, p.loc[lab.index]))
    out = pd.concat(preds).sort_index()
    print(f"Walk-forward: {len(preds)} pencere, ortalama AUC = {np.mean(aucs):.3f} "
          f"(0.50 = yazı-tura; 0.52+ gün içinde kayda değer)")
    return out


def save(m, path="model.pkl"):
    with open(path, "wb") as fh:
        pickle.dump(m, fh)


def load(path="model.pkl"):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return pickle.load(fh)
