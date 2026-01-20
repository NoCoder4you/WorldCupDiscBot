import responses


def test_discord_oauth_callback_sets_session(client):
    token_url = "https://discord.com/api/oauth2/token"
    me_url = "https://discord.com/api/users/@me"

    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, token_url, json={"access_token": "token-123"}, status=200)
        rsps.add(
            responses.GET,
            me_url,
            json={"id": "42", "username": "Tester", "discriminator": "0001", "avatar": "abc"},
            status=200,
        )

        with client.session_transaction() as sess:
            sess["oauth_state"] = "state-123"

        resp = client.get("/auth/discord/callback?code=abc&state=state-123")
        assert resp.status_code == 302

        with client.session_transaction() as sess:
            user = sess.get("wc_user")
            assert user["discord_id"] == "42"
            assert user["username"] == "Tester#0001"
