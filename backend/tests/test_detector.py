from fukidashi.detector import Detection, build_detections, iou, nms, reading_order


def test_iou_and_nms():
    a, b, c = (0, 0, 10, 10), (1, 1, 10, 10), (50, 50, 60, 60)
    assert iou(a, a) == 1 and iou(a, c) == 0
    kept = nms([(a, 0.9), (b, 0.5), (c, 0.7)], 0.5)
    assert [k[0] for k in kept] == [a, c]


def test_bubble_pairing_and_free_text():
    raw = [
        ("bubble", (0, 0, 100, 100), 0.9),
        ("text_bubble", (20, 20, 80, 80), 0.9),
        ("text_free", (300, 300, 340, 340), 0.8),
        ("text_bubble", (500, 500, 540, 540), 0.8),  # no bubble -> own box
        ("text_free", (21, 21, 79, 79), 0.6),  # duplicate of text_bubble
        ("text_free", (900, 900, 910, 910), 0.2),  # below threshold
    ]
    dets = build_detections(raw, "en")
    assert len(dets) == 3
    by = {d.text_box: d for d in dets}
    assert by[(20, 20, 80, 80)].box == (0, 0, 100, 100)
    assert by[(500, 500, 540, 540)].box == (500, 500, 540, 540)
    assert by[(300, 300, 340, 340)].kind == "text_free"


def mk(x, y):
    b = (x, y, x + 40, y + 40)
    return Detection(b, b, "text_bubble")


def test_reading_order_ja_rtl_rows():
    ds = [mk(0, 0), mk(100, 5), mk(50, 200), mk(150, 200)]
    ja = reading_order(ds, "ja")
    assert [d.box[0] for d in ja] == [100, 0, 150, 50]
    en = reading_order(ds, "en")
    assert [d.box[0] for d in en] == [0, 100, 50, 150]
