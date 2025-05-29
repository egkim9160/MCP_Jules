def format_results(results: list, format_flag: str) -> str:
    """
    Formats the search results based on a flag.
    - results: A list of result documents (job postings or user profiles).
    - format_flag: A string indicating the desired format (e.g., "summary", "detailed_list", "ids_only").
    Returns a formatted string.
    """
    if not results:
        return "No results found."

    output = f"--- Results (Format: {format_flag}) ---\n"
    if format_flag == "summary":
        for i, res in enumerate(results):
            title = res.get('title', res.get('name', f"Item {i+1}"))
            output += f"- {title}\n"
        if len(results) > 3:
             output += f"... and {len(results)-3} more.\n"
    elif format_flag == "detailed_list":
        for res in results:
            output += f"Details: {res}\n"
    elif format_flag == "ids_only":
        for res in results:
            output += f"{res.get('board_id') or res.get('user_id')}\n"
    else: 
        for res in results:
            output += f"{res}\n"
            
    return output
