> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Generate a structured document

> Generates a structured document using one of three template-supply paths: a stored template reference (optionally with runtime overrides), an ad-hoc assembly of stored sections, or a fully inline dynamic template. Exactly one of `templateRef`, `assemblyTemplate`, or `dynamicTemplate` must be provided.
Context can combine different types or reference an interactionId to automatically fetch existing context to pass to the LLM. Note that discarded facts are not passed to the LLM.
With the exception of the plain `templateRef` path (no overrides), every call creates a new auto-generated template aggregate that snapshots the resolved prompts as a drift-proof receipt, persisted for 30 days.




## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml post /documents/
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
  /documents/:
    post:
      tags:
        - Guided Documents
      summary: Generate a structured document
      description: >
        Generates a structured document using one of three template-supply
        paths: a stored template reference (optionally with runtime overrides),
        an ad-hoc assembly of stored sections, or a fully inline dynamic
        template. Exactly one of `templateRef`, `assemblyTemplate`, or
        `dynamicTemplate` must be provided.

        Context can combine different types or reference an interactionId to
        automatically fetch existing context to pass to the LLM. Note that
        discarded facts are not passed to the LLM.

        With the exception of the plain `templateRef` path (no overrides), every
        call creates a new auto-generated template aggregate that snapshots the
        resolved prompts as a drift-proof receipt, persisted for 30 days.
      operationId: guided_documents_generate
      parameters:
        - $ref: '#/components/parameters/Tenant-Name'
        - $ref: '#/components/parameters/X-Corti-Retention-Policy-Ephemeral'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/GuidedDocumentsGenerateRequest'
      responses:
        '200':
          description: OK — document was generated but not saved (retention policy `none`).
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GuidedDocumentsCreateEphemeralResponse'
        '201':
          description: Created — document was generated and saved.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/GuidedDocumentsCreateResponse'
        '400':
          $ref: '#/components/responses/BadRequest'
        '404':
          description: Referenced template, template version, or section was not found.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '422':
          description: >
            Request was syntactically valid but semantically rejected — for
            example, none of `templateRef`/`assemblyTemplate`/`dynamicTemplate`
            was supplied, the referenced template has no published version, or
            an override referenced a section that is not part of the base
            template.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '500':
          description: The downstream ML service failed to generate the document.
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
            await client.Documents.GenerateAsync(
                new GuidedDocumentsGenerateByTemplateRef
                {
                    OutputLanguage = "outputLanguage",
                    TemplateRef = new GuidedTemplateRef { TemplateId = "templateId" },
                }
            );
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
            await client.documents.generate({
                outputLanguage: "outputLanguage",
                templateRef: {
                    templateId: "templateId"
                }
            });
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
    X-Corti-Retention-Policy-Ephemeral:
      name: X-Corti-Retention-Policy
      in: header
      description: >-
        Pass the optional `X-Corti-Retention-Policy: none` header to generate
        and return the document without saving it to the database. The response
        will be 200 with `GuidedDocumentsCreateEphemeralResponse`. Without the
        header the document is saved and the response is 201 with
        `GuidedDocumentsCreateResponse`.
      required: false
      schema:
        type: string
        enum:
          - none
  schemas:
    GuidedDocumentsGenerateRequest:
      oneOf:
        - $ref: '#/components/schemas/GuidedDocumentsGenerateByTemplateRef'
          title: templateRef
        - $ref: '#/components/schemas/GuidedDocumentsGenerateByAssembly'
          title: assemblyTemplate
        - $ref: '#/components/schemas/GuidedDocumentsGenerateByDynamic'
          title: dynamicTemplate
    GuidedDocumentsCreateEphemeralResponse:
      type: object
      required:
        - document
        - usageInfo
      description: >
        Response when a document is generated but not saved (retention policy
        `none`).
      properties:
        document:
          $ref: '#/components/schemas/GuidedEphemeralDocument'
        usageInfo:
          $ref: '#/components/schemas/CommonUsageInfo'
    GuidedDocumentsCreateResponse:
      type: object
      required:
        - document
        - usageInfo
      description: Response when a document is generated and saved (default retention).
      properties:
        document:
          $ref: '#/components/schemas/GuidedDocument'
        usageInfo:
          $ref: '#/components/schemas/CommonUsageInfo'
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
    GuidedDocumentsGenerateByTemplateRef:
      description: >
        Generate a document using a stored template. Optionally supply runtime
        overrides to patch instructions or sections without mutating the base
        template. At least one of `context` or `interactionId` must be supplied
        as input context for the model.
      allOf:
        - $ref: '#/components/schemas/GuidedDocumentsGenerateBase'
        - type: object
          required:
            - templateRef
          properties:
            templateRef:
              $ref: '#/components/schemas/GuidedTemplateRef'
              description: >-
                Reference an existing stored template, optionally with
                overrides.
    GuidedDocumentsGenerateByAssembly:
      description: >
        Generate a document by assembling a template from existing stored
        sections. The resulting template aggregate is auto-saved and can be
        referenced in future calls. At least one of `context` or `interactionId`
        must be supplied as input context for the model.
      allOf:
        - $ref: '#/components/schemas/GuidedDocumentsGenerateBase'
        - type: object
          required:
            - assemblyTemplate
          properties:
            assemblyTemplate:
              $ref: '#/components/schemas/GuidedAssemblyRequest'
              description: Assemble a template from existing stored sections.
    GuidedDocumentsGenerateByDynamic:
      description: >
        Generate a document from a fully inline template definition supplied in
        the request body. Sections and the wrapping template are created and
        immediately published as auto-generated resources. At least one of
        `context` or `interactionId` must be supplied as input context for the
        model.
      allOf:
        - $ref: '#/components/schemas/GuidedDocumentsGenerateBase'
        - type: object
          required:
            - dynamicTemplate
          properties:
            dynamicTemplate:
              $ref: '#/components/schemas/GuidedDynamicRequest'
              description: Fully inline template defined in the request body.
    GuidedEphemeralDocument:
      type: object
      required:
        - name
        - templateId
        - templateVersionId
        - language
        - stringDocument
        - labels
      description: A generated document that was not saved to the database.
      properties:
        name:
          type: string
        templateId:
          type: string
          format: uuid
        templateVersionId:
          type: string
          format: uuid
        language:
          type: string
          description: The BCP 47 language tag of the generated output.
        interactionId:
          type: string
          format: uuid
          nullable: true
          description: >-
            The interaction whose context was used to generate this document, if
            supplied.
        stringDocument:
          type: object
          additionalProperties:
            type: string
        structuredDocument:
          type: object
          additionalProperties: true
          nullable: true
        labels:
          type: array
          description: Key/value labels attached to this document.
          items:
            $ref: '#/components/schemas/GuidedLabel'
    CommonUsageInfo:
      type: object
      description: Credits consumed for this request.
      required:
        - creditsConsumed
      properties:
        creditsConsumed:
          type: number
    GuidedDocument:
      type: object
      required:
        - id
        - name
        - templateId
        - templateVersionId
        - language
        - stringDocument
        - labels
        - createdAt
        - updatedAt
      description: A generated document saved to the database.
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
        templateId:
          type: string
          format: uuid
          description: >
            The template ID used for generation. For a plain `templateRef` with
            no overrides this is the referenced template. For other paths it is
            the newly saved auto-generated template aggregate.
        templateVersionId:
          type: string
          format: uuid
          description: The specific template version that was used for generation.
        language:
          type: string
          description: The BCP 47 language tag of the generated output.
        interactionId:
          type: string
          format: uuid
          nullable: true
          description: >-
            The interaction whose context was used to generate this document, if
            supplied.
        stringDocument:
          type: object
          description: >-
            The generated document as a map of section key to rendered string
            output.
          additionalProperties:
            type: string
        structuredDocument:
          description: The generated document as a structured object keyed by section.
          type: object
          additionalProperties: true
          nullable: true
        labels:
          type: array
          description: Key/value labels attached to this document.
          items:
            $ref: '#/components/schemas/GuidedLabel'
        createdAt:
          type: string
          format: date-time
        updatedAt:
          type: string
          format: date-time
    GuidedDocumentsGenerateBase:
      type: object
      required:
        - outputLanguage
      description: >
        Fields shared across all guided-document request variants.
        `outputLanguage` is always required. Exactly one of `context` (possible
        to combine different context types) or `interactionId` (API auto-fetches
        existing facts, transcripts) must be supplied as input for the model.
      properties:
        outputLanguage:
          type: string
          description: >-
            The language in which the document will be generated as a BCP 47
            tag.
        context:
          type: array
          description: >
            Ordered list of context items the model reasons over. Each item is
            one of text, a transcript (with optional metadata and segments), or
            a single fact. Items are interleaved by timestamps where present on
            transcript segments; otherwise array order is preserved.
          items:
            $ref: '#/components/schemas/GuidedDocumentContext'
        interactionId:
          type: string
          format: uuid
          description: >
            When supplied, all facts and transcripts already attached to the
            referenced interaction are passed implicitly as input context. Facts
            with `isDiscarded: true` are not passed on.
        labels:
          type: array
          description: >-
            Key/value labels attached to the document. Used for filtering in the
            LIST /documents endpoint.
          items:
            $ref: '#/components/schemas/GuidedLabel'
    GuidedTemplateRef:
      type: object
      required:
        - templateId
      properties:
        templateId:
          type: string
          format: uuid
          description: The UUID of a stored template.
        templateVersionId:
          type: string
          format: uuid
          nullable: true
          description: >-
            Optional explicit template version. Defaults to the template's
            published version when omitted.
        overrides:
          $ref: '#/components/schemas/GuidedTemplateOverrides'
          description: >
            Runtime overrides applied on top of the resolved template. When
            present, a new auto-generated template is persisted with
            `inheritedFromId` pointing at the base template.
    GuidedAssemblyRequest:
      type: object
      required:
        - name
        - sectionRefs
      description: >-
        Compose a template by referencing existing stored sections in
        declaration order.
      properties:
        name:
          type: string
          description: >-
            Name for the auto-generated template aggregate that will be
            persisted.
        instructions:
          $ref: '#/components/schemas/GuidedTemplateInstructions'
          description: Template-level instructions for the assembled template.
        sectionRefs:
          type: array
          minItems: 1
          items:
            $ref: '#/components/schemas/GuidedAssemblySectionRef'
    GuidedDynamicRequest:
      type: object
      required:
        - name
        - generation
      description: >-
        Fully inline template definition. Sections and the wrapping template are
        created and immediately published as auto-generated resources.
      properties:
        name:
          type: string
        generation:
          $ref: '#/components/schemas/GuidedDynamicInline'
    GuidedLabel:
      type: object
      required:
        - key
        - value
      properties:
        key:
          type: string
        value:
          type: string
    GuidedDocumentContext:
      oneOf:
        - $ref: '#/components/schemas/CommonTextContext'
          title: CommonTextContext
        - $ref: '#/components/schemas/CommonTranscriptContext'
          title: CommonTranscriptContext
        - $ref: '#/components/schemas/CommonFactsContext'
          title: CommonFactsContext
      discriminator:
        propertyName: type
        mapping:
          text:
            $ref: '#/components/schemas/CommonTextContext'
          transcript:
            $ref: '#/components/schemas/CommonTranscriptContext'
          facts:
            $ref: '#/components/schemas/CommonFactsContext'
    GuidedTemplateOverrides:
      type: object
      properties:
        instructions:
          $ref: '#/components/schemas/GuidedTemplateInstructions'
          description: Replaces the template-level instructions for this call.
        sections:
          type: array
          description: >-
            Per-section override patches. Each entry must reference a section
            already linked to the base template version.
          items:
            $ref: '#/components/schemas/GuidedSectionOverride'
    GuidedTemplateInstructions:
      type: object
      required:
        - prompt
      properties:
        prompt:
          type: string
          description: >-
            Template-level prompt instructions that apply generally to all
            sections.
    GuidedAssemblySectionRef:
      type: object
      required:
        - sectionId
      description: |
        Per-section reference for the assembly path. 
      properties:
        sectionId:
          type: string
          format: uuid
        sectionVersionId:
          type: string
          format: uuid
          nullable: true
          description: >-
            Optional explicit section version. Defaults to the section's
            published version when omitted.
        overrides:
          $ref: '#/components/schemas/GuidedSectionOverrides'
    GuidedDynamicInline:
      type: object
      required:
        - instructions
        - sections
      properties:
        instructions:
          $ref: '#/components/schemas/GuidedTemplateInstructions'
        sections:
          type: array
          minItems: 1
          items:
            $ref: '#/components/schemas/GuidedSectionGeneration'
    CommonTextContext:
      type: object
      title: Text
      required:
        - type
        - text
      properties:
        type:
          type: string
          enum:
            - text
          description: |
            The type of context, always "text" in this context.
        text:
          type: string
          description: |
            A text string to be used as input to the model.
          minLength: 1
    CommonTranscriptContext:
      type: object
      required:
        - type
        - transcript
      description: A transcript provided as input context to the model.
      properties:
        type:
          type: string
          enum:
            - transcript
        transcript:
          $ref: '#/components/schemas/GuidedDocumentTranscriptMinimal'
    CommonFactsContext:
      type: object
      required:
        - type
        - facts
      description: A list of facts provided as input context to the model.
      properties:
        type:
          type: string
          enum:
            - facts
        facts:
          type: array
          minItems: 1
          items:
            $ref: '#/components/schemas/GuidedDocumentFactMinimal'
    GuidedSectionOverride:
      type: object
      required:
        - sectionId
      description: >
        Override patch applied to a section linked to the base template version.
        Override semantics are per-field for `instructions` (any field you omit
        is inherited from the parent's published version) and wholesale for
        `outputSchema` (whatever you submit fully replaces the parent schema —
        partial schemas are not merged). The same rule applies when a section is
        forked via `inheritFromId`.
      properties:
        sectionId:
          type: string
          format: uuid
          description: The UUID of a section linked to the base template version.
        generation:
          $ref: '#/components/schemas/GuidedSectionOverrides'
    GuidedSectionOverrides:
      type: object
      description: >
        Patches a section's content at link time without mutating the underlying
        section. Override semantics are per-field for instructions (any field
        you omit is inherited from the parent's published version) and wholesale
        for `outputSchema` (whatever you submit fully replaces the parent
        schema). The same applies when a section is forked via `inheritFromId`.
      properties:
        heading:
          type: string
          nullable: true
          description: When provided, replaces the section's heading for this call.
        instructions:
          $ref: '#/components/schemas/GuidedSectionInstructionsOverride'
        outputSchema:
          $ref: '#/components/schemas/GuidedOutputSchema'
          description: When provided, fully replaces the parent's output schema.
    GuidedSectionGeneration:
      type: object
      required:
        - heading
        - instructions
        - outputSchema
      properties:
        heading:
          type: string
          description: The heading of this section. Passed to the LLM.
        instructions:
          $ref: '#/components/schemas/GuidedSectionInstructions'
          description: The prompt instructions for this section.
        outputSchema:
          $ref: '#/components/schemas/GuidedOutputSchema'
    GuidedDocumentTranscriptMinimal:
      type: object
      required:
        - transcripts
      description: >
        Minimal transcript shape accepted as guided-document input context.
        Decoupled from the transcript resource: only `transcripts` is required,
        and within each segment only `text` is required.
      properties:
        metadata:
          $ref: '#/components/schemas/GuidedDocumentTranscriptMetadataMinimal'
        transcripts:
          type: array
          minItems: 1
          items:
            $ref: '#/components/schemas/GuidedDocumentTranscriptSegmentMinimal'
    GuidedDocumentFactMinimal:
      type: object
      required:
        - text
      description: Minimal fact shape. Only `text` is required.
      properties:
        text:
          type: string
          description: The text of the fact.
          minLength: 1
        group:
          type: string
          description: The group to which the fact belongs.
          example: Others
    GuidedSectionInstructionsOverride:
      type: object
      description: >
        Partial section-instructions patch used in override and fork contexts.
        Each field is independent: provide only the fields you want to replace,
        and any field you omit is inherited from the parent's published version.
      properties:
        contentPrompt:
          type: string
          description: >-
            When provided, replaces the section's content prompt. Omit to
            inherit from the parent.
        writingStylePrompt:
          type: string
          description: >-
            When provided, replaces the section's writing style prompt. Omit to
            inherit from the parent.
        miscPrompt:
          type: string
          description: >-
            When provided, replaces the section's misc prompt. Omit to inherit
            from the parent.
    GuidedOutputSchema:
      oneOf:
        - $ref: '#/components/schemas/GuidedStringNode'
          title: String
          description: >-
            Outputs a string according to the optionally configurable schema
            requirements.
        - $ref: '#/components/schemas/GuidedNumberNode'
          title: Number
          description: >-
            Outputs a number. The model infers whether it should be an integer
            or float from context.
        - $ref: '#/components/schemas/GuidedBoolNode'
          title: Boolean
          description: Outputs a boolean true or false according to schema configuration.
        - $ref: '#/components/schemas/GuidedArrayNode'
          title: Array
          description: >-
            Outputs an array of items according to the optionally configurable
            schema requirements. Items can be configured as any type of node.
        - $ref: '#/components/schemas/GuidedObjectNode'
          title: Object
          description: >-
            The object output type offers advanced schema configuration with the
            ability to define for each field value any of the outputSchema
            types.
      discriminator:
        propertyName: type
        mapping:
          string:
            $ref: '#/components/schemas/GuidedStringNode'
          number:
            $ref: '#/components/schemas/GuidedNumberNode'
          boolean:
            $ref: '#/components/schemas/GuidedBoolNode'
          object:
            $ref: '#/components/schemas/GuidedObjectNode'
          array:
            $ref: '#/components/schemas/GuidedArrayNode'
    GuidedSectionInstructions:
      type: object
      required:
        - contentPrompt
      properties:
        contentPrompt:
          type: string
          description: >-
            The content prompt instructs the model what to include for
            synthesis. For `documentationMode: routed_parallel` this impacts
            what facts to route to this section.
        writingStylePrompt:
          type: string
          description: >-
            The writingStyle prompt instructs the model in what tone and style
            to output.
        miscPrompt:
          type: string
          description: >-
            Optional free-form prompt for any instructions that don't fit
            contentPrompt or writingStylePrompt.
    GuidedDocumentTranscriptMetadataMinimal:
      type: object
      description: Optional transcript-level metadata. All fields optional.
      properties:
        participantsRoles:
          type: array
          items:
            $ref: '#/components/schemas/TranscriptsParticipant'
          nullable: true
    GuidedDocumentTranscriptSegmentMinimal:
      type: object
      required:
        - text
      description: Minimal transcript segment. Only `text` is required.
      properties:
        channel:
          type: integer
          description: The channel associated with this phrase/utterance.
        participant:
          type: integer
          description: The identifier of the participant.
        speakerId:
          type: integer
          description: Id to tag an identified speaker.
        text:
          type: string
          description: The spoken phrase or utterance.
          minLength: 1
        start:
          type: integer
          description: Start time in milliseconds for phrase/utterance.
        end:
          type: integer
          description: End time in milliseconds for phrase/utterance.
    GuidedStringNode:
      type: object
      required:
        - type
      properties:
        type:
          type: string
          enum:
            - string
        description:
          type: string
          description: >-
            Guide the LLM in what to output for this node. Supplements the
            section-level instructions.
        default:
          type: string
          nullable: true
          description: >-
            If nothing is outputted, this default is used. When `enum` is set,
            the default must be one of the enum values.
        enum:
          type: array
          description: Can be used to guide the LLM with specific values to output.
          items:
            type: string
        pattern:
          type: string
          nullable: true
          description: Can be used to constrain the LLM to output a specific pattern.
    GuidedNumberNode:
      type: object
      required:
        - type
      properties:
        type:
          type: string
          enum:
            - number
        description:
          type: string
          description: >-
            Guide the LLM in what to output for this node. Supplements the
            section-level instructions.
        default:
          type: number
          nullable: true
          description: If nothing is outputted, this default is used.
        enum:
          type: array
          description: Can be used to guide the LLM with specific values to output.
          items:
            type: number
        minimum:
          type: number
          description: Use if a minimum value applies.
          nullable: true
        maximum:
          type: number
          description: Use if a maximum value applies.
          nullable: true
    GuidedBoolNode:
      type: object
      required:
        - type
      properties:
        type:
          type: string
          enum:
            - boolean
        description:
          type: string
          description: >-
            Guide the LLM in what to output for this node. Supplements the
            section-level instructions.
        default:
          type: boolean
          description: If nothing is outputted, this default is used.
          nullable: true
    GuidedArrayNode:
      type: object
      required:
        - type
        - items
      properties:
        type:
          type: string
          enum:
            - array
        description:
          type: string
          description: >-
            Guide the LLM in what to output for this node. Supplements the
            section-level instructions.
        items:
          description: >-
            Must be another output schema node (string, number, boolean, array,
            or object).
          allOf:
            - $ref: '#/components/schemas/GuidedOutputSchema'
        itemFormat:
          type: string
          default: |
            - {item}
          description: >
            Format string used to render each array item in the generated
            output. Use the `{item}` placeholder for the item value.
          example: |
            - {item}
        minItems:
          type: integer
          minimum: 0
          description: Minimum number of array items to generate.
          nullable: true
        maxItems:
          type: integer
          minimum: 0
          description: Maximum number of array items to generate.
          nullable: true
    GuidedObjectNode:
      type: object
      required:
        - type
      properties:
        type:
          type: string
          enum:
            - object
        description:
          type: string
          description: >-
            Guide the LLM in what to output for this node. Supplements the
            section-level instructions.
        fieldFormat:
          type: string
          default: |
            {key}: {value}
          description: >
            Free-form format string that controls how an object's fields are
            rendered into the final text output. Operates in one of two modes
            determined by which placeholders appear:


            **Subheading mode** (default: `"{key}: {value}\n"`): triggered when
            the format contains both `{key}` and `{value}`. Applied per field —
            each field becomes a key/value line. When a field has no relevant
            input/output and no `default` is set, the entire key/value line for
            that field is omitted from the rendered output.


            **Object mode** (e.g. `"{name} ({age})"`): triggered when `{key}`
            and `{value}` are absent. Placeholders must be actual field keys
            defined in `fields`. Applied once for the whole object, composing
            all fields into a single string. When a field has no relevant
            input/output and no `default` is set, its placeholder is replaced
            with an empty string (`""`).


            Validation rules: format must not be empty; if either `{key}` or
            `{value}` appears, both must be present; in subheading mode no extra
            placeholders are allowed; in object mode every placeholder must
            match a defined field key.
          example: |
            {key}: {value}
        fields:
          type: array
          description: Define what fields are possible to return in the object.
          items:
            $ref: '#/components/schemas/GuidedFieldDefinition'
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
    GuidedFieldDefinition:
      type: object
      required:
        - key
        - description
        - value
      properties:
        key:
          type: string
          description: Use to set a key to reference.
        description:
          type: string
          description: >-
            Guide the LLM in what to output for this node. Supplements the
            section-level instructions.
        value:
          description: >-
            Must be another output schema node (string, number, boolean, array,
            or object).
          allOf:
            - $ref: '#/components/schemas/GuidedOutputSchema'
        default:
          type: string
          nullable: true
          description: >-
            If nothing is outputted for this field, this default value is used
            in the rendered output.
    TranscriptsParticipantRoleEnum:
      type: string
      enum:
        - doctor
        - patient
        - multiple
  responses:
    BadRequest:
      description: Bad Request
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ErrorResponse'
  securitySchemes:
    AuthorizationHeader:
      type: http
      description: Input your token
      scheme: bearer

````