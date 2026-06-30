> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# List Transcripts

> Retrieves a list of transcripts for a given interaction.



## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml get /interactions/{id}/transcripts/
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
  /interactions/{id}/transcripts/:
    get:
      tags:
        - Transcripts
      summary: List Transcripts
      description: Retrieves a list of transcripts for a given interaction.
      operationId: transcripts_list
      parameters:
        - $ref: '#/components/parameters/Tenant-Name'
        - $ref: '#/components/parameters/CommonInteractionId'
        - name: full
          in: query
          description: Display full transcripts in listing
          schema:
            type: boolean
            description: Display full transcripts in listing
      responses:
        '200':
          description: Returns a list of transcripts associated with the interaction.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TranscriptsListResponse'
        '400':
          description: RFC9457
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '401':
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
          source: |
            using Corti;

            var client = new CortiClient(
                "TENANT_NAME",
                CortiClientEnvironment.Eu,
                new CortiClientAuth.ClientCredentials("client_id", "client_secret")
            );
            await client.Transcripts.ListAsync(
                "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                new TranscriptsListRequest()
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

            await
            client.transcripts.list("f47ac10b-58cc-4372-a567-0e02b2c3d479");
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
    TranscriptsListResponse:
      type: object
      required:
        - transcripts
      properties:
        transcripts:
          nullable: true
          type: array
          items:
            $ref: '#/components/schemas/TranscriptsListItem'
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
    TranscriptsListItem:
      type: object
      required:
        - id
        - transcriptSample
      properties:
        id:
          $ref: '#/components/schemas/UUID'
          type: string
          format: uuid
          description: The unique identifier of the transcript.
          items: {}
        transcriptSample:
          type: string
        transcript:
          $ref: '#/components/schemas/TranscriptsData'
          type: object
          nullable: true
    TranscriptsData:
      type: object
      required:
        - metadata
        - transcripts
      properties:
        metadata:
          $ref: '#/components/schemas/TranscriptsMetadata'
          type: object
          description: >-
            Additional information about the participants involved in the
            transcript.
        transcripts:
          type: array
          description: An array of transcripts.
          items:
            $ref: '#/components/schemas/CommonTranscriptResponse'
    TranscriptsMetadata:
      type: object
      properties:
        participantsRoles:
          type: array
          items:
            $ref: '#/components/schemas/TranscriptsParticipant'
          nullable: true
    CommonTranscriptResponse:
      type: object
      required:
        - channel
        - participant
        - speakerId
        - text
        - start
        - end
      properties:
        channel:
          type: integer
          description: The channel associated with this phrase/utterance.
        participant:
          type: integer
          description: The identifier of the participant.
        speakerId:
          type: integer
          description: Id to tag an identified speaker. Auto-increments.
        text:
          type: string
          description: The spoken phrase or utterance extracted from the audio.
        start:
          type: integer
          description: Start time in milliseconds for phrase/utterance.
        end:
          type: integer
          description: End time in milliseconds for phrase/utterance.
    TranscriptsParticipant:
      type: object
      required:
        - channel
        - role
      properties:
        channel:
          type: integer
          description: The audio channel to associate with a participant role.
        role:
          $ref: '#/components/schemas/TranscriptsParticipantRoleEnum'
          description: >-
            The role of the participant (e.g., 'doctor', 'patient', use
            'multiple' for single channel).
    TranscriptsParticipantRoleEnum:
      type: string
      enum:
        - doctor
        - patient
        - multiple
  securitySchemes:
    AuthorizationHeader:
      type: http
      description: Input your token
      scheme: bearer

````