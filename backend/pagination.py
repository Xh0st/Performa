from math import ceil


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def normalize_pagination(page: int, page_size: int) -> tuple[int, int]:
    current_page = max(1, page)
    size = min(MAX_PAGE_SIZE, max(1, page_size))
    return current_page, size


async def fetch_page(collection, filter_query, sort, page: int, page_size: int, projection=None):
    current_page, size = normalize_pagination(page, page_size)
    total = await collection.count_documents(filter_query)
    cursor = collection.find(filter_query, projection).sort(sort)
    documents = await cursor.skip((current_page - 1) * size).limit(size).to_list(size)
    return documents, total, current_page, size


def page_response(items: list, total: int, page: int, page_size: int, **extra) -> dict:
    response = {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, ceil(total / page_size)),
    }
    response.update(extra)
    return response