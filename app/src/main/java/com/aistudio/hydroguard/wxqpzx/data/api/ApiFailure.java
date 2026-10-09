package com.aistudio.hydroguard.wxqpzx.data.api;

public class ApiFailure extends Exception {
    public final String endpoint;
    public final Integer statusCode;
    public final Kind kind;

    public enum Kind { SERVER_UNREACHABLE, AUTHENTICATION, INSUFFICIENT_DATA, API_ERROR, MALFORMED_RESPONSE }

    public ApiFailure(Kind kind, String endpoint, Integer statusCode, String message, Throwable cause) {
        super(message, cause);
        this.kind = kind;
        this.endpoint = endpoint;
        this.statusCode = statusCode;
    }
}
