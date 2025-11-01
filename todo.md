# TODO

- Make the message tool separate for each agent if possible
- Improve prompts for better multi-agent calling in sequence for a large task
- Join all the tools into one file per agent
- Unify credentials


# auth

**Web OAuth Flow**

- Create a `Flow` instance (`Flow.from_client_secrets_file(...)`) with your client secret JSON, Gmail scopes, and the public `redirect_uri`. This object tracks everything Google needs to know about your app during the OAuth handshake.  
- Call `flow.authorization_url(...)` to generate two things: `auth_url`, which is the Google consent URL you send the user to, and `state`, a random string you must persist (session/DB) so you can validate the callback and prevent CSRF.  
- Redirect the user’s browser to `auth_url`. After login and consent, Google sends the user back to the `redirect_uri` you registered, appending `code=<authorization_code>` and `state=<same_random_string>`. Your server must expose that callback route, read the query params, and confirm the incoming `state` matches what you stored.  
- In the callback handler, you now exchange the short-lived authorization code for OAuth tokens by calling `flow.fetch_token(authorization_response=request.url)`. Pass the entire callback URL (including scheme, host, code, state) from the incoming request—Google’s client library parses it, verifies the state, and sends the code to Google’s token endpoint.  
- When `fetch_token` returns successfully, `flow.credentials` holds the resulting `Credentials` object: `credentials.token` (access token), `credentials.refresh_token` (if `access_type="offline"`), `credentials.expiry`, and scope metadata. Serialize it (`credentials.to_json()`), store it securely per user, and use it later when building the Gmail API service.