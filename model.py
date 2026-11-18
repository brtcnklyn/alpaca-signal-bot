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


def tune_threshold(df: pd.DataFrame, cost: float, val_days: int = 5, min_trades: int = 30,
                   explore_top: float = 0.02):
    """Kendini ayarlama: son 'val_days' günü ayırıp önceki günlerle eğitir, ayrılan günlerde
    en güçlü sinyallerin hangi diliminin (en iyi %1, %2, ... %20) maliyet sonrası en çok
    kazandırdığını bulur. Olasılıkların seviyesi etiket oranına bağlı olduğu için eşik sabit
    sayı değil, bu dilimin olasılık değeridir. (eşik, bilgi) döndürür; bilgi['exit'] çıkış eşiği."""
    d = df.dropna(subset=FEATURES + ["label", "fwd_ret"])
    dates = np.array(d.index.get_level_values("timestamp").date)
    days = sorted(set(dates))
    if len(days) <= val_days + 10:
        return None, None
    cut = days[-val_days]
    tr, va = d[dates < cut], d[dates >= cut]
    m = train(tr)
    p = m.predict_proba(va[FEATURES])[:, 1]
    net = va["fwd_ret"].values - 2 * cost
    best = None
    for top in (0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.20):
        th = float(np.quantile(p, 1 - top))
        sel = p > th
        n = int(sel.sum())
        if n < min_trades:
            continue
        mean = float(net[sel].mean())
        cand = (mean * n, th, n, mean, float((net[sel] > 0).mean()), top)
        if best is None or cand[0] > best[0]:
            best = cand
    exit_th = float(np.median(p))
    if best is None or best[3] <= 0:
        # Keşif modu: hiçbir dilim maliyeti karşılamadı. Deneme hesabında yine de en güçlü
        # %explore_top sinyalle işlem yapılır; sonuçlar learn.py ile sembol cezalarına döner.
        th = float(np.quantile(p, 1 - explore_top))
        sel = p > th
        n = int(sel.sum())
        mean = float(net[sel].mean()) if n else 0.0
        win = float((net[sel] > 0).mean()) if n else 0.0
        return th, {"n": n, "mean": mean, "win": win, "top": explore_top, "exit": exit_th, "kesif": True}
    return best[1], {"n": best[2], "mean": best[3], "win": best[4], "top": best[5], "exit": exit_th}


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
