from arena.graph import build_app


def test_graph_builds():
    app = build_app()

    assert app is not None


def test_graph_has_invoke():
    app = build_app()

    assert hasattr(app, "invoke")


def test_graph_has_stream():
    app = build_app()

    assert hasattr(app, "stream")