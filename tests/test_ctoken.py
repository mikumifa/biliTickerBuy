from util.CTokenUtil import CTokenSnapshot, init_ctoken_state


def test_generate_ctoken_matches_real_sample():
    token = CTokenSnapshot(
        m1=245,
        touchend=0,
        m2=58,
        visibilitychange=0,
        m3=183,
        m4=189,
        openWindow=1,
        m5=228,
        timer=4,
        timediff=226.112,
        m6=126,
        m7=129,
        m8=136,
        m9=62,
    )

    assert token.generate_ctoken() == "9QAAADoAAAC3AL0AAQDkAAAABAAAAOIAfgCBAIgAPgA="


def test_generate_ctoken_matches_second_real_sample():
    token = CTokenSnapshot(
        m1=245,
        touchend=0,
        m2=58,
        visibilitychange=0,
        m3=183,
        m4=189,
        openWindow=1,
        m5=228,
        timer=5,
        timediff=713.802,
        m6=126,
        m7=129,
        m8=136,
        m9=62,
    )

    assert token.generate_ctoken() == "9QAAADoAAAC3AL0AAQDkAAAABQACAMkAfgCBAIgAPgA="


def test_generate_ctoken_matches_third_real_sample():
    token = CTokenSnapshot(
        m1=245,
        touchend=0,
        m2=58,
        visibilitychange=0,
        m3=183,
        m4=189,
        openWindow=1,
        m5=228,
        timer=8,
        timediff=766.034,
        m6=126,
        m7=129,
        m8=136,
        m9=62,
    )

    assert token.generate_ctoken() == "9QAAADoAAAC3AL0AAQDkAAAACAACAP4AfgCBAIgAPgA="


if __name__ == "__main__":
    test_generate_ctoken_matches_third_real_sample()
    test_generate_ctoken_matches_second_real_sample()
    test_generate_ctoken_matches_real_sample()
    snapshot = init_ctoken_state().snapshot()
    snapshot.touchend = 3  # 位置 1
    snapshot.visibilitychange = 0  # 位置3
    snapshot.m5 = 145  # 位置7
    snapshot.openWindow = 0  # 位置6
    snapshot.timediff = 0  # 位置 10

    #     [
    #   [1, "H", H],
    #   [2, "Q", Q],
    #   [3, "z", z],
    #   [4, "Y", Y],
    #   [5, "K", K],
    #   [6, "W", W],
    #   [7, "J", J],
    #   [8, "X", X],
    #   [9, "$", $],
    #   [10, "Z", Z],
    #   [11, "ee", ee],
    # ]
