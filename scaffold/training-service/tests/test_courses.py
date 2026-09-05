async def test_create_and_get_course(client, auth_train):
    r = await client.post(
        "/api/v1/courses",
        json={"title": "Firearms Requalification", "validity_months": 12, "mandatory": True},
        headers=auth_train,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Firearms Requalification"
    assert body["validity_months"] == 12
    assert body["mandatory"] is True

    r = await client.get(f"/api/v1/courses/{body['id']}", headers=auth_train)
    assert r.status_code == 200
    assert r.json()["title"] == "Firearms Requalification"


async def test_create_course_defaults_mandatory_false(client, auth_train):
    r = await client.post(
        "/api/v1/courses",
        json={"title": "Defensive Driving", "validity_months": 24},
        headers=auth_train,
    )
    assert r.status_code == 201, r.text
    assert r.json()["mandatory"] is False


async def test_create_course_requires_training_cert_write(client, auth_none):
    r = await client.post(
        "/api/v1/courses",
        json={"title": "Firearms Requalification", "validity_months": 12},
        headers=auth_none,
    )
    assert r.status_code == 403


async def test_list_courses(client, auth_train, make_course):
    await make_course(title="A")
    await make_course(title="B")
    r = await client.get("/api/v1/courses", headers=auth_train)
    assert r.status_code == 200
    titles = {c["title"] for c in r.json()}
    assert {"A", "B"} <= titles


async def test_get_unknown_course_404(client, auth_train):
    r = await client.get("/api/v1/courses/999999", headers=auth_train)
    assert r.status_code == 404


async def test_update_course(client, auth_train, make_course):
    course = await make_course(title="Old Title", validity_months=6)
    r = await client.patch(
        f"/api/v1/courses/{course.id}",
        json={"title": "New Title", "validity_months": 12},
        headers=auth_train,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "New Title"
    assert body["validity_months"] == 12
    assert body["mandatory"] is False  # untouched field unchanged


async def test_update_unknown_course_404(client, auth_train):
    r = await client.patch(
        "/api/v1/courses/999999", json={"title": "X"}, headers=auth_train
    )
    assert r.status_code == 404


async def test_delete_course(client, auth_train, make_course):
    course = await make_course()
    r = await client.delete(f"/api/v1/courses/{course.id}", headers=auth_train)
    assert r.status_code == 204

    r = await client.get(f"/api/v1/courses/{course.id}", headers=auth_train)
    assert r.status_code == 404


async def test_delete_course_still_referenced_by_certification_409(
    client, auth_train, make_certification
):
    cert = await make_certification()
    r = await client.delete(f"/api/v1/courses/{cert.course_id}", headers=auth_train)
    assert r.status_code == 409


async def test_courses_require_auth(client):
    r = await client.get("/api/v1/courses")
    assert r.status_code == 401
