> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# List Facts

> Retrieves a list of facts for a given interaction.



## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml get /interactions/{id}/facts/
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
  /interactions/{id}/facts/:
    get:
      tags:
        - Facts
      summary: List Facts
      description: Retrieves a list of facts for a given interaction.
      operationId: facts_list
      parameters:
        - $ref: '#/components/parameters/Tenant-Name'
        - $ref: '#/components/parameters/CommonInteractionId'
      responses:
        '200':
          description: Returns a list of facts associated with the specified interaction.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/FactsListResponse'
        '504':
          description: RFC9457
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
      x-codeSamples:
        - lang: csharp
          label: C# .NET SDK
          source: >
            using Corti;


            var client = new CortiClient(
                "TENANT_NAME",
                CortiClientEnvironment.Eu,
                new CortiClientAuth.ClientCredentials("client_id", "client_secret")
            );

            await
            client.Facts.ListAsync("f47ac10b-58cc-4372-a567-0e02b2c3d479");
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
            await client.facts.list("f47ac10b-58cc-4372-a567-0e02b2c3d479");
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
    FactsListResponse:
      type: object
      required:
        - facts
      properties:
        facts:
          type: array
          description: A list of facts associated with the interaction.
          items:
            $ref: '#/components/schemas/FactsListItem'
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
    FactsListItem:
      type: object
      properties:
        id:
          type: string
          format: uuid
          description: The unique identifier of the fact.
          items: {}
          example: 3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08
        text:
          type: string
          description: The text content of the fact.
        group:
          type: string
          description: The key identifying the group to which the fact belongs.
          example: other
        groupId:
          $ref: '#/components/schemas/UUID'
          type: string
          format: uuid
          description: The unique identifier of the group to which the fact belongs.
          items: {}
        isDiscarded:
          type: boolean
          description: >-
            Indicates whether the fact has been marked as discarded by an
            end-user.
        source:
          $ref: '#/components/schemas/CommonSourceEnum'
          description: >-
            Source 'core' indicates facts generated by the LLM, 'user' for facts
            added by the user, 'system' for system-derived facts (e.g. EHR).
        createdAt:
          type: string
          format: date-time
          description: The timestamp when the fact was created.
        updatedAt:
          type: string
          format: date-time
          description: The timestamp when the fact was last updated.
        evidence:
          type: array
          items:
            $ref: '#/components/schemas/FactsEvidence'
    CommonSourceEnum:
      type: string
      enum:
        - core
        - system
        - user
    FactsEvidence:
      type: object
      properties:
        type:
          type: string
          description: The category of evidence.
        reference:
          type: string
          description: A reference that supports the fact.
        quote:
          type: string
          description: >-
            A direct excerpt or phrase extracted from the reference source that
            justifies the fact.
  securitySchemes:
    AuthorizationHeader:
      type: http
      description: Input your token
      scheme: bearer

````