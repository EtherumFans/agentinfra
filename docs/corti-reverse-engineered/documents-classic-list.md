> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# List Documents

> List Documents



## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml get /interactions/{id}/documents/
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
  /interactions/{id}/documents/:
    get:
      tags:
        - Documents (Classic)
      summary: List Documents
      description: List Documents
      operationId: documents_list
      parameters:
        - $ref: '#/components/parameters/Tenant-Name'
        - $ref: '#/components/parameters/CommonInteractionId'
      responses:
        '200':
          description: ' '
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DocumentsListResponse'
        '400':
          description: RFC9457
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '403':
          description: RFC9457
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '500':
          description: RFC9457
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
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
            client.Documents.ListAsync("f47ac10b-58cc-4372-a567-0e02b2c3d479");
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
            await client.documents.list("f47ac10b-58cc-4372-a567-0e02b2c3d479");
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
    DocumentsListResponse:
      type: object
      required:
        - data
      properties:
        data:
          type: array
          items:
            $ref: '#/components/schemas/DocumentsGetResponse'
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
    DocumentsGetResponse:
      type: object
      required:
        - id
        - name
        - templateRef
        - isStream
        - sections
        - createdAt
        - updatedAt
        - outputLanguage
        - usageInfo
      properties:
        id:
          $ref: '#/components/schemas/UUID'
          type: string
          format: uuid
          description: Unique ID of the generated document
        name:
          type: string
          description: Name of the generated document
        templateRef:
          type: string
          description: Reference for the used template
        isStream:
          type: boolean
        sections:
          type: array
          description: Individual document sections
          items:
            $ref: '#/components/schemas/DocumentsSection'
        createdAt:
          type: string
          format: date-time
          description: The original timestamp when the document was created.
        updatedAt:
          type: string
          format: date-time
          description: The timestamp when the document was last updated.
        outputLanguage:
          type: string
          description: >-
            The language in which the document will be generated. Check
            https://docs.corti.ai/stt/languages for more.
        usageInfo:
          $ref: '#/components/schemas/CommonUsageInfo'
          type: object
    DocumentsSection:
      type: object
      required:
        - key
        - name
        - text
        - sort
        - createdAt
        - updatedAt
      properties:
        key:
          type: string
          description: Document section key
        name:
          type: string
          description: >-
            Name or heading of the document section within the generated
            document
        text:
          type: string
          description: Contents of the document section within the generated document
        sort:
          type: integer
          description: Order of the document section within the generated document
        createdAt:
          type: string
          format: date-time
          description: The original timestamp when the document section was created.
        updatedAt:
          type: string
          format: date-time
          description: The timestamp when the document section was last updated.
    CommonUsageInfo:
      type: object
      description: Credits consumed for this request.
      required:
        - creditsConsumed
      properties:
        creditsConsumed:
          type: number
  securitySchemes:
    AuthorizationHeader:
      type: http
      description: Input your token
      scheme: bearer

````