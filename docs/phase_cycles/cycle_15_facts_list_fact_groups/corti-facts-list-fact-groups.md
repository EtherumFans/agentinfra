> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# List Fact Groups

> Returns a list of available fact groups, used to categorize facts associated with an interaction.



## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml get /factgroups/
openapi: 3.0.0
info:
  title: Corti API
  version: 2.0.0
servers:
  - url: https://api.{environment}.corti.app/v2/
    variables:
      environment:
        default: eu
        enum:
          - us
          - eu
security:
  - AuthorizationHeader:
      - bearer
tags:
  - name: Interactions
  - name: Recordings
  - name: Transcripts
  - name: Facts
  - name: Codes
  - name: Languages
  - name: Guided Documents
  - name: Guided Templates
  - name: Guided Sections
  - name: Documents (Classic)
  - name: Templates (Classic)
paths:
  /factgroups/:
    get:
      tags:
        - Facts
      summary: List Fact Groups
      description: >-
        Returns a list of available fact groups, used to categorize facts
        associated with an interaction.
      operationId: facts_fact_groups_list
      parameters:
        - $ref: '#/components/parameters/Tenant-Name'
      responses:
        '200':
          description: >-
            Returns a list of available fact groups, used to categorize facts
            associated with an interaction.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/FactsFactGroupsListResponse'
        '500':
          description: RFC9457
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
      x-codeSamples:
        - lang: csharp
          label: C# .NET SDK
          source: |
            using Corti;

            var client = new CortiClient(
                "TENANT_NAME",
                CortiClientEnvironment.Eu,
                new CortiClientAuth.ClientCredentials("client_id", "client_secret")
            );
            await client.Facts.FactGroupsListAsync();
        - lang: javascript
          label: JavaScript SDK
          source: |
            import { CortiClient, CortiEnvironment } from "@corti/sdk";

            const client = new CortiClient({
                environment: CortiEnvironment.Eu,
                auth: {
                    clientId: "YOUR_CLIENT_ID",
                    clientSecret: "YOUR_CLIENT_SECRET"
                },
                tenantName: "YOUR_TENANT_NAME"
            });
            await client.facts.factGroupsList();
components:
  parameters:
    Tenant-Name:
      name: Tenant-Name
      in: header
      description: >-
        Identifies a distinct entity within Corti's multi-tenant system. Ensures
        correct routing and authentication of the request.
      required: true
      example: base
      schema:
        type: string
        description: >-
          Identifies a distinct entity within Corti's multi-tenant system.
          Ensures correct routing and authentication of the request.
        example: base
  schemas:
    FactsFactGroupsListResponse:
      type: object
      required:
        - data
      properties:
        data:
          type: array
          items:
            $ref: '#/components/schemas/FactsFactGroupsItem'
    ErrorResponse:
      type: object
      required:
        - requestid
        - status
        - type
        - detail
      properties:
        requestid:
          type: string
        status:
          type: integer
        type:
          type: string
        detail:
          type: string
        validationErrors:
          type: array
          items:
            type: object
            additionalProperties:
              type: string
    FactsFactGroupsItem:
      type: object
      properties:
        id:
          $ref: '#/components/schemas/UUID'
          type: string
          format: uuid
          items: {}
        key:
          type: string
        translations:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              languages_id:
                type: string
              name:
                type: string
    UUID:
      type: string
      items: {}
      format: uuid
      example: f47ac10b-58cc-4372-a567-0e02b2c3d479
  securitySchemes:
    AuthorizationHeader:
      type: http
      description: Input your token
      scheme: bearer

````