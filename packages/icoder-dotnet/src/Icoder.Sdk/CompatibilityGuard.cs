namespace Icoder.Sdk;

internal static class Guard
{
    public static void NotNull(object? value, string parameterName)
    {
        if (value is null)
        {
            throw new ArgumentNullException(parameterName);
        }
    }

    public static void NotNullOrWhiteSpace(string? value, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException("Value cannot be null or whitespace.", parameterName);
        }
    }

    public static void NotDisposed(bool disposed, object instance)
    {
        if (disposed)
        {
            throw new ObjectDisposedException(instance.GetType().FullName);
        }
    }
}
