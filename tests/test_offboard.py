from workgraph.offboard import redistribute


def _edges():
    # anna + bob co-edit shared.docx; anna + bob + carol co-edit team.docx;
    # anna is the SOLE contributor to secret.docx.
    return [
        {"actor": "anna@ex.com", "entity_id": "doc::shared", "weight": 4.0},
        {"actor": "bob@ex.com",  "entity_id": "doc::shared", "weight": 1.0},
        {"actor": "anna@ex.com", "entity_id": "doc::team",   "weight": 3.0},
        {"actor": "bob@ex.com",  "entity_id": "doc::team",   "weight": 1.0},
        {"actor": "carol@ex.com","entity_id": "doc::team",   "weight": 1.0},
        {"actor": "anna@ex.com", "entity_id": "doc::secret", "weight": 5.0},
    ]


def test_sole_contributor_flagged_orphaned():
    plan = {p.entity_id: p for p in redistribute("anna@ex.com", _edges())}
    assert plan["doc::secret"].orphaned_knowledge is True
    assert plan["doc::secret"].deltas == {}


def test_proportional_redistribution_to_co_contributors():
    plan = {p.entity_id: p for p in redistribute("anna@ex.com", _edges())}

    # shared: only bob remains -> gets all of anna's residual weight (4.0)
    shared = plan["doc::shared"]
    assert shared.orphaned_knowledge is False
    assert abs(shared.deltas["bob@ex.com"] - 4.0) < 1e-9

    # team: anna's 3.0 split between bob(1) and carol(1) -> 1.5 each
    team = plan["doc::team"]
    assert abs(team.deltas["bob@ex.com"] - 1.5) < 1e-9
    assert abs(team.deltas["carol@ex.com"] - 1.5) < 1e-9


def test_residual_weight_is_conserved():
    plan = redistribute("anna@ex.com", _edges())
    for p in plan:
        if not p.orphaned_knowledge:
            assert abs(sum(p.deltas.values()) - p.leaver_weight) < 1e-9


def test_leaver_with_no_edges_yields_nothing():
    assert redistribute("nobody@ex.com", _edges()) == []
