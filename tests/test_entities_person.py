from shadow.memory import EntityExtractor


def test_titled_name_extracted():
    e = EntityExtractor()
    result = e.extract("Met with Dr. Sharma about the project.")
    people = [r for r in result if r["type"] == "person"]
    assert len(people) == 1
    assert people[0]["name"] == "Sharma"


def test_mr_titled_name():
    e = EntityExtractor()
    result = e.extract("Mr. Patel sent an email.")
    people = [r for r in result if r["type"] == "person"]
    assert any(p["name"] == "Patel" for p in people)


def test_email_header_extracted():
    e = EntityExtractor()
    text = "From: alice@example.com\nSubject: hello"
    result = e.extract(text)
    people = [r for r in result if r["type"] == "person"]
    assert any(p["name"] == "Alice" for p in people)


def test_email_header_to_field():
    e = EntityExtractor()
    text = "To: bob@company.org\nCc: carol@x.io"
    result = e.extract(text)
    names = {r["name"] for r in result if r["type"] == "person"}
    assert "Bob" in names
    assert "Carol" in names


def test_handle_extracted():
    e = EntityExtractor()
    result = e.extract("thanks @priya for the review")
    people = [r for r in result if r["type"] == "person"]
    assert any(p["name"] == "priya" for p in people)


def test_full_name_extracted():
    e = EntityExtractor()
    result = e.extract("Naitik Sharma is working on this.")
    people = [r for r in result if r["type"] == "person"]
    assert any(p["name"] == "Naitik Sharma" for p in people)


def test_stopword_not_person():
    e = EntityExtractor()
    result = e.extract("GitHub is great.")
    people = [r for r in result if r["type"] == "person"]
    assert people == []


def test_project_name_not_double_labelled_as_person():
    e = EntityExtractor(known_projects=["SHADOW"])
    result = e.extract("Working on SHADOW today.")
    people = [r for r in result if r["type"] == "person"]
    assert not any(p["name"] == "SHADOW" for p in people)


def test_month_not_person():
    e = EntityExtractor()
    result = e.extract("Meeting on January 15.")
    people = [r for r in result if r["type"] == "person"]
    assert not any(p["name"] == "January" for p in people)


def test_weekday_not_person():
    e = EntityExtractor()
    result = e.extract("See you Monday.")
    people = [r for r in result if r["type"] == "person"]
    assert people == []


def test_email_lowercase_capitalized():
    e = EntityExtractor()
    result = e.extract("From: JOHN@example.com")
    people = [r for r in result if r["type"] == "person"]
    assert any(p["name"] == "John" for p in people)


def test_titled_name_with_hyphen():
    e = EntityExtractor()
    result = e.extract("Dr. Smith-Jones presented.")
    people = [r for r in result if r["type"] == "person"]
    assert any(p["name"] == "Smith-Jones" for p in people)


def test_prof_title():
    e = EntityExtractor()
    result = e.extract("Prof. Verma is teaching.")
    people = [r for r in result if r["type"] == "person"]
    assert any(p["name"] == "Verma" for p in people)


def test_person_and_topic_coexist():
    e = EntityExtractor()
    result = e.extract("Naitik Sharma is working on the ONNX project.")
    kinds = {r["type"] for r in result}
    assert "person" in kinds
    assert "topic" in kinds or "project" in kinds


def test_empty_text_returns_nothing():
    e = EntityExtractor()
    assert e.extract("") == []
