from cptoken import generate_ctoken


def test_generate_ctoken_matches_real_sample():
    token = generate_ctoken(
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

    assert token == "9QAAADoAAAC3AL0AAQDkAAAABAAAAOIAfgCBAIgAPgA="


def test_generate_ctoken_matches_second_real_sample():
    token = generate_ctoken(
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

    assert token == "9QAAADoAAAC3AL0AAQDkAAAABQACAMkAfgCBAIgAPgA="


def test_generate_ctoken_matches_third_real_sample():
    token = generate_ctoken(
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

    assert token == "9QAAADoAAAC3AL0AAQDkAAAACAACAP4AfgCBAIgAPgA="
