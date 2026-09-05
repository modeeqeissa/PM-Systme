import uuid


async def test_create_performance_review(client, auth_hr, make_officer):
    officer = await make_officer()
    reviewer = await make_officer(rank="Inspector")
    r = await client.post(
        f"/api/v1/officers/{officer.id}/performance-reviews",
        json={"reviewer_id": str(reviewer.id), "period": "2026-H1", "score": "87.50"},
        headers=auth_hr,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["period"] == "2026-H1"
    assert body["reviewer_id"] == str(reviewer.id)


async def test_create_performance_review_with_comments(client, auth_hr, make_officer):
    officer = await make_officer()
    reviewer = await make_officer(rank="Inspector")
    r = await client.post(
        f"/api/v1/officers/{officer.id}/performance-reviews",
        json={
            "reviewer_id": str(reviewer.id),
            "period": "2026-H1",
            "score": "87.50",
            "comments": "Consistently exceeds expectations on case throughput.",
        },
        headers=auth_hr,
    )
    assert r.status_code == 201, r.text
    assert r.json()["comments"] == "Consistently exceeds expectations on case throughput."


async def test_create_performance_review_comments_default_to_null(client, auth_hr, make_officer):
    officer = await make_officer()
    reviewer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/performance-reviews",
        json={"reviewer_id": str(reviewer.id), "period": "2026-H1", "score": "80"},
        headers=auth_hr,
    )
    assert r.status_code == 201, r.text
    assert r.json()["comments"] is None


async def test_patch_performance_review_comments(client, auth_hr, make_officer):
    officer = await make_officer()
    reviewer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/performance-reviews",
        json={"reviewer_id": str(reviewer.id), "period": "2026-H1", "score": "80"},
        headers=auth_hr,
    )
    review_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/performance-reviews/{review_id}",
        json={"comments": "Follow-up added after mid-cycle check-in."},
        headers=auth_hr,
    )
    assert r.status_code == 200
    assert r.json()["comments"] == "Follow-up added after mid-cycle check-in."


async def test_create_performance_review_unknown_officer_404(client, auth_hr, make_officer):
    reviewer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{uuid.uuid4()}/performance-reviews",
        json={"reviewer_id": str(reviewer.id), "period": "2026-H1", "score": "80"},
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_create_performance_review_unknown_reviewer_404(client, auth_hr, make_officer):
    officer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/performance-reviews",
        json={"reviewer_id": str(uuid.uuid4()), "period": "2026-H1", "score": "80"},
        headers=auth_hr,
    )
    assert r.status_code == 404


async def test_create_performance_review_score_out_of_range_422(client, auth_hr, make_officer):
    officer = await make_officer()
    reviewer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/performance-reviews",
        json={"reviewer_id": str(reviewer.id), "period": "2026-H1", "score": "150"},
        headers=auth_hr,
    )
    assert r.status_code == 422


async def test_create_performance_review_requires_hr_performance_write(
    client, auth_cmd, make_officer
):
    officer = await make_officer()
    reviewer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/performance-reviews",
        json={"reviewer_id": str(reviewer.id), "period": "2026-H1", "score": "80"},
        headers=auth_cmd,
    )
    assert r.status_code == 403


async def test_get_update_delete_performance_review(client, auth_hr, make_officer):
    officer = await make_officer()
    reviewer = await make_officer()
    r = await client.post(
        f"/api/v1/officers/{officer.id}/performance-reviews",
        json={"reviewer_id": str(reviewer.id), "period": "2026-H1", "score": "70.00"},
        headers=auth_hr,
    )
    review_id = r.json()["id"]

    r = await client.get(f"/api/v1/performance-reviews/{review_id}", headers=auth_hr)
    assert r.status_code == 200

    r = await client.patch(
        f"/api/v1/performance-reviews/{review_id}", json={"score": "95.00"}, headers=auth_hr
    )
    assert r.status_code == 200
    assert r.json()["score"] == "95.00"

    r = await client.delete(f"/api/v1/performance-reviews/{review_id}", headers=auth_hr)
    assert r.status_code == 204

    r = await client.get(f"/api/v1/performance-reviews/{review_id}", headers=auth_hr)
    assert r.status_code == 404


async def test_officer_performance_review_history(client, auth_hr, make_officer):
    officer = await make_officer()
    reviewer = await make_officer()
    await client.post(
        f"/api/v1/officers/{officer.id}/performance-reviews",
        json={"reviewer_id": str(reviewer.id), "period": "2025-H2", "score": "60"},
        headers=auth_hr,
    )
    await client.post(
        f"/api/v1/officers/{officer.id}/performance-reviews",
        json={"reviewer_id": str(reviewer.id), "period": "2026-H1", "score": "70"},
        headers=auth_hr,
    )

    r = await client.get(
        f"/api/v1/officers/{officer.id}/performance-reviews", headers=auth_hr
    )
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 2
    assert history[0]["period"] == "2026-H1"  # newest first
