async def test_create_and_get_certification(client, auth_train, make_course):
    course = await make_course()
    r = await client.post(
        "/api/v1/certifications", json={"course_id": course.id}, headers=auth_train
    )
    assert r.status_code == 201, r.text
    cert_id = r.json()["id"]
    assert r.json()["course_id"] == course.id

    r = await client.get(f"/api/v1/certifications/{cert_id}", headers=auth_train)
    assert r.status_code == 200
    assert r.json()["course_id"] == course.id


async def test_create_certification_unknown_course_404(client, auth_train):
    r = await client.post(
        "/api/v1/certifications", json={"course_id": 999999}, headers=auth_train
    )
    assert r.status_code == 404


async def test_create_certification_requires_training_cert_write(
    client, auth_none, make_course
):
    course = await make_course()
    r = await client.post(
        "/api/v1/certifications", json={"course_id": course.id}, headers=auth_none
    )
    assert r.status_code == 403


async def test_list_certifications_filter_by_course(client, auth_train, make_course, make_certification):
    course_a = await make_course()
    course_b = await make_course()
    await make_certification(course=course_a)
    await make_certification(course=course_b)

    r = await client.get(
        "/api/v1/certifications", params={"course_id": course_a.id}, headers=auth_train
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["course_id"] == course_a.id


async def test_get_unknown_certification_404(client, auth_train):
    r = await client.get("/api/v1/certifications/999999", headers=auth_train)
    assert r.status_code == 404


async def test_delete_certification(client, auth_train, make_certification):
    cert = await make_certification()
    r = await client.delete(f"/api/v1/certifications/{cert.id}", headers=auth_train)
    assert r.status_code == 204

    r = await client.get(f"/api/v1/certifications/{cert.id}", headers=auth_train)
    assert r.status_code == 404


async def test_delete_certification_still_issued_409(client, auth_train, make_certification):
    import uuid

    cert = await make_certification()
    await client.post(
        "/api/v1/officer-certifications",
        json={"officer_id": str(uuid.uuid4()), "certification_id": cert.id},
        headers=auth_train,
    )
    r = await client.delete(f"/api/v1/certifications/{cert.id}", headers=auth_train)
    assert r.status_code == 409


async def test_certifications_require_auth(client):
    r = await client.get("/api/v1/certifications")
    assert r.status_code == 401
