> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Update Fact

> Updates an existing fact associated with a specific interaction.



## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml patch /interactions/{id}/facts/{factId}
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
  /interactions/{id}/facts/{factId}:
    patch:
      tags:
        - Facts
      summary: Update Fact
      description: Updates an existing fact associated with a specific interaction.
      operationId: facts_update
      parameters:
        - $ref: '#/components/parameters/Tenant-Name'
        - $ref: '#/components/parameters/CommonInteractionId'
        - name: factId
          in: path
          description: The unique identifier of the fact to update. Must be a valid UUID.
          required: true
          schema:
            type: string
            format: uuid
            example: 3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08
            description: The unique identifier of the fact to update. Must be a valid UUID.
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/FactsUpdateRequest'
        required: true
      responses:
        '200':
          description: Returns the updated fact, including updated fields.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/FactsUpdateResponse'
        '504':
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
            await client.Facts.UpdateAsync(
                "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08",
                new FactsUpdateRequest()
            );
        - lang: javascript
          label: JavaScript SDK
          source: >
            import { CortiClient, CortiEnvironment } from "@corti/sdk";


            const client = new CortiClient({
                environment: CortiEnvironment.Eu,
                auth: {
                    clientId: "YOUR_CLIENT_ID",
                    clientSecret: "YOUR_CLIENT_SECRET"
                },
                tenantName: "YOUR_TENANT_NAME"
            });

            await client.facts.update("f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08");
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
    CommonInteractionId:
      name: id
      in: path
      description: The unique identifier of the interaction. Must be a valid UUID.
      required: true
      schema:
        $ref: '#/components/schemas/UUID'
  schemas:
    FactsUpdateRequest:
      type: object
      properties:
        text:
          type: string
          description: The updated text of the fact.
        group:
          type: string
          description: The updated group key for the fact.
          example: other
        source:
          $ref: '#/components/schemas/CommonSourceEnum'
          description: >-
            To track the updated source of the fact. Set to 'user' to indicate a
            change by an end-user.
        isDiscarded:
          type: boolean
          description: >-
            Set this to true if discarded by an end-user, then filter out from
            the document generation request.
    FactsUpdateResponse:
      type: object
      required:
        - id
        - text
        - group
        - groupId
        - source
        - isDiscarded
        - createdAt
        - updatedAt
      properties:
        id:
          type: string
          format: uuid
          description: The unique identifier of the fact.
          items: {}
          example: 3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08
        text:
          type: string
          description: The updated text content of the fact.
        group:
          type: string
          description: The updated group key to which the fact belongs.
          example: other
        groupId:
          $ref: '#/components/schemas/UUID'
          type: string
          format: uuid
          description: The unique identifier of the associated group.
          items: {}
        source:
          $ref: '#/components/schemas/CommonSourceEnum'
          description: The updated origin of the fact.
        isDiscarded:
          type: boolean
          description: Indicates whether the fact is marked as discarded.
        createdAt:
          type: string
          format: date-time
          description: The original timestamp when the fact was created.
        updatedAt:
          type: string
          format: date-time
          description: The timestamp when the fact was last updated.
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
    UUID:
      type: string
      items: {}
      format: uuid
      example: f47ac10b-58cc-4372-a567-0e02b2c3d479
    CommonSourceEnum:
      type: string
      enum:
        - core
        - system
        - user
  securitySchemes:
    AuthorizationHeader:
      type: http
      description: Input your token
      scheme: bearer

````