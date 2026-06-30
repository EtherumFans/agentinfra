> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# List sections

> Returns a list of sections and their metadata. Fetch a sectionId to get the full generation content.
Use query parameters to filter by language, region, specialty, label, publish status, or source.




## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml get /documents/sections/
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
  /documents/sections/:
    get:
      tags:
        - Guided Sections
      summary: List sections
      description: >
        Returns a list of sections and their metadata. Fetch a sectionId to get
        the full generation content.

        Use query parameters to filter by language, region, specialty, label,
        publish status, or source.
      operationId: guided_sections_list
      parameters:
        - $ref: '#/components/parameters/Tenant-Name'
        - name: lang
          in: query
          description: >-
            Filter sections by BCP 47 language tag (e.g. `fr`, `de`, or
            `en-GB`). Repeatable.
          schema:
            type: array
            items:
              type: string
          style: form
          explode: true
        - name: region
          in: query
          description: >-
            Filter sections by ISO 3166-1 alpha-3 region code (e.g. `BEL`).
            Repeatable.
          schema:
            type: array
            items:
              type: string
          style: form
          explode: true
        - name: specialty
          in: query
          description: Filter sections by clinical specialty. Repeatable.
          schema:
            type: array
            items:
              type: string
          style: form
          explode: true
        - name: label
          in: query
          description: >-
            Filter sections by label in `key:value` format. Repeatable; matches
            sections that have any of the given labels.
          schema:
            type: array
            items:
              type: string
          style: form
          explode: true
        - name: published
          in: query
          description: >-
            Filter by publish status. Omit to return both published and
            unpublished items; set to `true` for published only, `false` for
            unpublished only.
          schema:
            type: boolean
        - name: source
          in: query
          description: >-
            Filter by source. Omit to return both. `user` returns only
            user-created sections; `corti` returns only Corti standard sections.
          schema:
            $ref: '#/components/schemas/GuidedSourceFilter'
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/GuidedSection'
      x-codeSamples:
        - lang: csharp
          label: C# .NET SDK
          source: >
            using Corti.Documents;

            using Corti;


            var client = new CortiClient(
                "TENANT_NAME",
                CortiClientEnvironment.Eu,
                new CortiClientAuth.ClientCredentials("client_id", "client_secret")
            );

            await client.Documents.Sections.ListAsync(new
            GuidedSectionsListRequest());
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
            await client.documents.sections.list();
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
    GuidedSourceFilter:
      type: string
      description: Filter by content source.
      enum:
        - user
        - corti
    GuidedSection:
      type: object
      required:
        - id
        - name
        - languages
        - regions
        - specialties
        - labels
        - createdAt
        - updatedAt
      properties:
        id:
          description: The UUID of the section.
          type: string
          format: uuid
        inheritedFromId:
          description: >-
            Reference to the section to inherit generation configuration from.
            Inherits from published version by default.
          type: string
          format: uuid
          nullable: true
        autoGenerated:
          description: >-
            True if the section was auto-generated as part of an inline
            section-composed POST /documents request.
          type: boolean
        source:
          description: >-
            Whether this section was created by the user, a project-related API
            Client or is a Corti standard resource.
          type: string
          enum:
            - user
            - corti
            - project
        name:
          description: The name of the section.
          type: string
        languages:
          description: >-
            BCP 47 languages this section has been tweaked for. Empty means no
            language-specific tweaks.
          type: array
          items:
            type: string
        regions:
          description: >-
            ISO 3166-1 alpha-3 country codes this section has been tweaked for.
            Empty means no region-specific tweaks.
          type: array
          items:
            type: string
        specialties:
          description: >-
            Clinical specialties this section has been tweaked for. Empty means
            no specialty-specific tweaks.
          type: array
          items:
            type: string
        description:
          description: The description for the section.
          type: string
        labels:
          description: >-
            The labels available to use as query param filter in the LIST
            /sections endpoint.
          type: array
          items:
            $ref: '#/components/schemas/GuidedLabel'
        publishedVersion:
          $ref: '#/components/schemas/GuidedSectionVersion'
          description: >-
            The currently published version with section inheritance fully
            resolved. Present when a version has been published.
        createdBy:
          description: The UUID of the creator of this section.
          type: string
          format: uuid
        createdAt:
          description: The original timestamp when the section was created.
          type: string
          format: date-time
        updatedAt:
          description: The original timestamp when the section was last updated.
          type: string
          format: date-time
        deletedAt:
          description: >-
            Present when the section has been deleted. GET by ID still returns
            the full resource with this field populated.
          type: string
          format: date-time
          nullable: true
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
    GuidedSectionVersion:
      type: object
      description: >
        A section version. When embedded inside a Section resource (e.g. GET
        /sections/:id),

        inheritance is fully resolved. When returned directly from version
        endpoints

        (GET/LIST/POST .../versions/...), contains raw authored values without
        inheritance.
      required:
        - id
        - versionNumber
        - generation
      properties:
        id:
          description: The UUID of the section version.
          type: string
          format: uuid
        versionNumber:
          description: Starts at 0 and auto-increments.
          type: integer
        deletedAt:
          description: Present when the section version has been deleted.
          type: string
          format: date-time
          nullable: true
        generation:
          $ref: '#/components/schemas/GuidedSectionGeneration'
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
  securitySchemes:
    AuthorizationHeader:
      type: http
      description: Input your token
      scheme: bearer

````