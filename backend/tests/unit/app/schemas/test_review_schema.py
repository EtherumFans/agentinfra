from app.schemas.review import ReviewResponse


def test_review_response_preserves_non_orm_and_model_used_configuration() -> None:
    assert ReviewResponse.model_config["from_attributes"] is False
    assert ReviewResponse.model_config["protected_namespaces"] == ()
