from datetime import timedelta
from itertools import islice

import networkx as nx
from sqlalchemy import select, func

from app.models import Account, Alert, Customer, Transaction

WINDOW = timedelta(hours=24)       # bounded time window, as the blueprint recommends
HUB_DEGREE = 40                    # safety net: accounts with more links than this are treated as hubs
OPEN_STATUSES = ["open", "in_review", "in_case"]


def build_graph(db, as_of, window=WINDOW):
    """Accounts are nodes; transfers are directed edges with total amount and count."""
    rows = db.execute(
        select(Transaction.source_account_id, Transaction.destination_account_id, Transaction.amount)
        .where(Transaction.occurred_at > as_of - window, Transaction.occurred_at <= as_of)).all()
    G = nx.DiGraph()
    for s, d, a in rows:
        if G.has_edge(s, d):
            G[s][d]["amount"] += float(a)
            G[s][d]["count"] += 1
        else:
            G.add_edge(s, d, amount=float(a), count=1)
    # Institutions (employers, utilities) are linked to almost everyone, so they would make every
    # account look "connected". Business accounts and very high-degree nodes are left out.
    business = set(db.scalars(select(Account.id).join(Customer, Customer.id == Account.customer_id)
                              .where(Customer.customer_type == "business")))
    hubs = {n for n in G if G.degree(n) > HUB_DEGREE} | (business & set(G.nodes))
    G.remove_nodes_from(hubs)
    return G


def _neighbourhood(G, account_id, max_nodes=60):
    """The account plus everything within 2 hops (1 hop if that is too crowded to draw)."""
    U = G.to_undirected()
    ego = nx.ego_graph(U, account_id, radius=2)
    if len(ego) > max_nodes:
        ego = nx.ego_graph(U, account_id, radius=1)
    return G.subgraph(ego.nodes)


def graph_signals(db, account_id, as_of):
    """Returns (graph score between 0 and 1, evidence dictionary)."""
    G = build_graph(db, as_of)
    if account_id not in G:
        return 0.0, {}
    sub = _neighbourhood(G, account_id)
    ind, outd = G.in_degree(account_id), G.out_degree(account_id)
    cycles = list(islice(nx.simple_cycles(sub, length_bound=4), 20)) if len(sub) <= 200 else []
    neighbours = [n for n in sub.nodes if n != account_id]
    flagged = 0
    if neighbours:
        flagged = db.scalar(select(func.count(func.distinct(Alert.account_id))).where(
            Alert.account_id.in_(neighbours), Alert.status.in_(OPEN_STATUSES))) or 0
    my_out = set(G.successors(account_id))
    shared = sum(1 for n in neighbours if len(my_out & set(G.successors(n))) >= 2)

    fan = min(ind / 10, 1) * min(outd / 4, 1)               # many senders in AND many beneficiaries out
    score = (0.35 * fan + 0.25 * (1 if cycles else 0)
             + 0.25 * min(flagged / 2, 1) + 0.15 * min(shared / 3, 1))   # illustrative weights
    evidence = {"distinct_senders": ind, "distinct_beneficiaries": outd,
                "connected_accounts_2hop": len(neighbours), "short_cycles_nearby": len(cycles),
                "neighbours_with_open_alerts": flagged, "accounts_sharing_beneficiaries": shared}
    return round(float(score), 4), evidence


def ego_graph_payload(db, account_id, as_of):
    """Nodes and links for the picture on the Alert detail page."""
    G = build_graph(db, as_of)
    if account_id not in G:
        return {"nodes": [], "links": []}
    sub = _neighbourhood(G, account_id)
    ids = list(sub.nodes)
    refs = {a.id: a.account_ref for a in db.scalars(select(Account).where(Account.id.in_(ids)))}
    flagged = set(db.scalars(select(Alert.account_id).where(
        Alert.account_id.in_(ids), Alert.status.in_(OPEN_STATUSES))))

    def group(n):
        return "focus" if n == account_id else "flagged" if n in flagged else "linked"

    return {"nodes": [{"id": refs.get(n, str(n)), "group": group(n)} for n in ids],
            "links": [{"source": refs.get(u, str(u)), "target": refs.get(v, str(v)), "value": d["amount"]}
                      for u, v, d in sub.edges(data=True)]}