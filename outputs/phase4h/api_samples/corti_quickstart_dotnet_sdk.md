# Corti .NET SDK — Install + First Request

Source: Corti Console > Developer Quickstart
URL: https://console.corti.app/project/b8f8129a-c31d-407f-b723-6ecc592d31e4/developer-quickstart
Use case selected: Build a medical coding app
SDK tab: .NET SDK

## Install

```bash
dotnet add package Corti.Sdk
```

## Sample code (creates an Interaction)

```csharp
using Corti;

var client = new CortiClient(
    Environment.GetEnvironmentVariable("CORTI_TENANT_NAME"),
    Environment.GetEnvironmentVariable("CORTI_ENVIRONMENT"),
    new CortiClientAuth.ClientCredentials(
        Environment.GetEnvironmentVariable("CORTI_CLIENT_ID"),
        Environment.GetEnvironmentVariable("CORTI_CLIENT_SECRET")
    )
);

var created = await client.Interactions.CreateAsync(new InteractionsCreateRequest
{
    Encounter = new InteractionsEncounterCreateRequest
    {
        Identifier = Guid.NewGuid().ToString(), // Replace with your own identifier
        Status = InteractionsEncounterStatusEnum.Planned,
        Type = InteractionsEncounterTypeEnum.FirstConsultation,
    },
});
```

## Env vars required

Same as JS SDK: `CORTI_ENVIRONMENT` + `CORTI_CLIENT_ID` + `CORTI_CLIENT_SECRET` + `CORTI_TENANT_NAME`.

## Observations

- `CortiClient` constructor takes `(tenantName, environment, CortiClientAuth.ClientCredentials(clientId, clientSecret))`
- Naming convention: PascalCase (e.g., `InteractionsCreateRequest`, `InteractionsEncounterCreateRequest`)
- Strongly-typed enums: `InteractionsEncounterStatusEnum.Planned`, `InteractionsEncounterTypeEnum.FirstConsultation`
- Async pattern: `CreateAsync` returns a Task
- Same surface as JS SDK — focused on `Interactions` (Encounter creation), no `Agents` or `Experts` surface in the Quickstart
