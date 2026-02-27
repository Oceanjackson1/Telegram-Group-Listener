from utils.validators import format_identifier


def mask_url(url: str) -> str:
    if len(url) <= 52:
        return url
    return f"{url[:48]}..."


def build_summary_text(i18n, language: str, config: dict, title_key: str, include_status: bool = False) -> str:
    monitor_type = config.get("monitor_type", "person")
    if monitor_type == "keyword":
        source_group = config.get("keyword_source")
        destination = config.get("keyword_destination", {})
        keywords = config.get("keywords", [])

        destination_type = destination.get("type")
        if destination_type == "lark":
            destination_type_text = i18n.t(language, "dest_type_lark")
            destination_label = i18n.t(language, "destination_label_url")
            destination_value = mask_url(destination.get("value", "-"))
        else:
            destination_type_text = i18n.t(language, "dest_type_telegram")
            destination_label = i18n.t(language, "destination_label_group")
            destination_value = format_identifier(destination.get("value"))

        payload = {
            "title": i18n.t(language, title_key),
            "source_group": format_identifier(source_group),
            "keywords": ", ".join(keywords) if keywords else "-",
            "destination_type": destination_type_text,
            "destination_label": destination_label,
            "destination_value": destination_value,
            "confirm_question": i18n.t(language, "confirm_question"),
        }

        if include_status:
            payload["status"] = i18n.t(language, "status_active" if config.get("keyword_active") else "status_inactive")
            return i18n.t(language, "status_template_keyword", **payload)

        return i18n.t(language, "summary_template_keyword", **payload)

    source = config.get("source", {})
    destination = config.get("destination", {})

    destination_type = destination.get("type")
    if destination_type == "lark":
        destination_type_text = i18n.t(language, "dest_type_lark")
        destination_label = i18n.t(language, "destination_label_url")
        destination_value = mask_url(destination.get("value", "-"))
    else:
        destination_type_text = i18n.t(language, "dest_type_telegram")
        destination_label = i18n.t(language, "destination_label_group")
        destination_value = format_identifier(destination.get("value"))

    payload = {
        "title": i18n.t(language, title_key),
        "source_group": format_identifier(source.get("group")),
        "source_user": format_identifier(source.get("user")),
        "destination_type": destination_type_text,
        "destination_label": destination_label,
        "destination_value": destination_value,
        "confirm_question": i18n.t(language, "confirm_question"),
    }

    if include_status:
        payload["status"] = i18n.t(language, "status_active" if config.get("active") else "status_inactive")
        return i18n.t(language, "status_template", **payload)

    return i18n.t(language, "summary_template", **payload)
