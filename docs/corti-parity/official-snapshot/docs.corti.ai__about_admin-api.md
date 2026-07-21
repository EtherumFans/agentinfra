> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Introduction to the Administration API

> Programmatic access to manage your Corti Console account

## What is the Admin API?

The `Admin API` lets you manage your Corti Console programmatically. It is built for administrators who want to automate account operations.

<Warning>
  This `Admin API` is separate from the `Corti API` used for speech to text, text generation, and agentic workflows:

  * Authentication and scope for the `Admin API` uses email-and-password to obtain a bearer token via `/auth/token`. This token is only used for API administration.

  * The `Admin API` endpoints `/customers` and `/users` are only enabled and exposed for projects with Embedded Assistant.

  Please [contact us](mailto:help@corti.ai) if you have interest in this functionality or further questions.
</Warning>

### Use Cases

The following functionality is currently supported by the `Admin API`:

| Feature              | Functionality                                                            | Scope                            |
| :------------------- | :----------------------------------------------------------------------- | :------------------------------- |
| **Authentication**   | Authenticate user and get access token                                   | All projects                     |
| **Manage Customers** | Create, update, list, and delete customer accounts within your project   | Projects with Embedded Assistant |
| **Manage Users**     | Create, update, list, and delete users associated with customer accounts | Projects with Embedded Assistant |

<Tip>Permissions mirror the Corti Console - only project admins or owners can create, update, or delete resources.</Tip>

## Quickstart

<Steps titleSize="h3">
  <Step title="Prepare your Corti Console account">
    * Sign up or log in at [console.corti.app](https://console.corti.app/)
    * Ensure your account has a password set

    <Tip>
      Best practice: use a dedicated service account for Admin API automation. Assign only the minimal required role and rotate credentials regularly.
    </Tip>
  </Step>

  <Step title="Authenticate and get an access token">
    Call `/auth/token` with your Console email and password to obtain a JWT access token.
    See API Reference: [Authenticate user and get access token](/api-reference/admin/auth/authenticate-user-and-get-access-token)

    ```bash theme={null}
    curl -X POST https://api.console.corti.app/functions/v1/public/auth/token \
      -H "Content-Type: application/json" \
      -d '{
        "email": "your-email@example.com",
        "password": "your-password"
      }'
    ```

    Example response:

    ```json theme={null}
    {
      "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "tokenType": "bearer",
      "expiresIn": 3600
    }
    ```
  </Step>

  <Step title="Call an endpoint with the token">
    Include the token in the Authorization header for subsequent requests:

    ```bash theme={null}
    curl -X GET https://api.console.corti.app/functions/v1/public/projects/{projectId}/customers \
      -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    ```

    <Tip>
      Tokens expire after `expiresIn` seconds. Once expired, call the `auth/token` endpoint again to obtain a new token.
    </Tip>
  </Step>
</Steps>

***

## Top Pages

<Card title="Authenticate" icon="key" href="/api-reference/admin/auth/authenticate-user-and-get-access-token" horizontal>
  Obtain an access token
</Card>

<Card title="Create customer" icon="building" href="/api-reference/admin/customers/create-a-new-customer" horizontal>
  Create a new customer in a project
</Card>

<Card title="Create user" icon="user" href="/api-reference/admin/users/create-a-new-user-and-add-it-to-the-customer" horizontal>
  Create a new user within a customer
</Card>

<br />

<Note>Please [contact us](mailto:help@corti.ai) for support or more information</Note>
