from app.database import engine
from app.models import Base


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Database schema created.")


if __name__ == "__main__":
    main()
