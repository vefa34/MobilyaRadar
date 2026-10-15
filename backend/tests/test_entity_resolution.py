from sqlalchemy import func, select

from app.connectors.base import RawCompany
from app.models import Company, CompanyAlias, CompanyLocation, EntityMatchReview
from app.services.entity_resolution import SourcePolicy, resolve_record

P = SourcePolicy("brave_search")


def raw(name, **kw):
    kw.setdefault("country", "DE")
    kw.setdefault("source_key", "brave_search")
    return RawCompany(name=name, **kw)


def count(db, model=Company):
    return db.scalar(select(func.count(model.id)))


def test_name_variants_with_same_domain_merge(db, org):
    names = ["ABC Furniture LLC", "ABC Furnitures", "ABC Möbel GmbH", "ABC Furniture Trading"]
    results = [resolve_record(db, org.id, raw(n, city="Berlin", website="https://www.abc-moebel.de"), P) for n in names]
    db.commit()
    assert results[0].created and not any(r.created for r in results[1:])
    assert count(db) == 1
    assert count(db, CompanyAlias) >= 4


def test_same_core_name_same_city_merges_without_domain(db, org):
    resolve_record(db, org.id, raw("ABC Möbel GmbH", city="Berlin"), P)
    m = resolve_record(db, org.id, raw("ABC Furniture", city="Berlin"), P)
    assert not m.created and "same distinctive name, same city" in m.reasons


def test_branch_in_other_city_becomes_location(db, org):
    a = resolve_record(db, org.id, raw("ABC Furniture", city="Berlin", address="Hauptstr. 1, Berlin", website="abc-moebel.de"), P)
    b = resolve_record(db, org.id, raw("ABC Furniture - Hamburg Branch", city="Hamburg", address="Elbweg 5, Hamburg",
                                       website="abc-moebel.de"), P)
    db.commit()
    assert a.company.id == b.company.id
    locs = db.scalars(select(CompanyLocation).where(CompanyLocation.company_id == a.company.id)).all()
    assert {loc.city for loc in locs} == {"Berlin", "Hamburg"}


def test_same_name_different_city_without_identifiers_goes_to_review(db, org):
    resolve_record(db, org.id, raw("Nordwind Möbel", city="Berlin"), P)
    m = resolve_record(db, org.id, raw("Nordwind Möbel", city="München"), P)
    db.commit()
    assert m.created and m.review_queued
    assert count(db) == 2 and count(db, EntityMatchReview) == 1


def test_conflicting_registration_numbers_veto_merge(db, org):
    resolve_record(db, org.id, raw("Atlas Möbel", city="Berlin", registration_number="HRB 1111", website="atlas.de"), P)
    m = resolve_record(db, org.id, raw("Atlas Möbel", city="Berlin", registration_number="HRB 2222", website="atlas.de"), P)
    assert m.created


def test_generic_words_do_not_create_matches(db, org):
    resolve_record(db, org.id, raw("Nordlicht Furniture Trading", city="Batumi", country="GE", website="nordlicht.ge"), P)
    m = resolve_record(db, org.id, raw("Garnet Furniture Trading", city="Batumi", country="GE", website="garnet.ge"), P)
    assert m.created and not m.review_queued


def test_phone_match_merges(db, org):
    resolve_record(db, org.id, raw("Casa Bella", city="Casablanca", country="MA", phone="0522 123 456"), P)
    m = resolve_record(db, org.id, raw("Casa Bella Meubles SARL", city="Casablanca", country="MA", phone="+212 522 123456"), P)
    assert not m.created


def test_scripts_are_aliases_not_new_companies(db, org):
    a = resolve_record(db, org.id, raw("ავეჯის სახლი", city="Tbilisi", country="GE", website="aveji-saxli.ge",
                                       alt_names=["Aveji Sakhli"]), P)
    b = resolve_record(db, org.id, raw("Aveji Sakhli LLC", city="Tbilisi", country="GE", website="https://aveji-saxli.ge"), P)
    db.commit()
    assert a.company.id == b.company.id
    assert a.company.name_original_script == "ავეჯის სახლი" and a.company.name_transliterated


def test_same_source_record_is_idempotent(db, org):
    r = raw("Möbelhaus X", city="Köln", source_key="osm_overpass", source_record_id="node/1")
    resolve_record(db, org.id, r, SourcePolicy("osm_overpass"))
    m = resolve_record(db, org.id, r, SourcePolicy("osm_overpass"))
    assert not m.created and count(db) == 1


def test_tenant_isolation(db, org):
    from app.models import Organization
    other = Organization(name="Other")
    db.add(other)
    db.commit()
    resolve_record(db, org.id, raw("Shared Name Möbel", city="Berlin", website="shared.de"), P)
    m = resolve_record(db, other.id, raw("Shared Name Möbel", city="Berlin", website="shared.de"), P)
    assert m.created  # never merged across organisations


def test_storage_disallowed_source_is_not_persisted(db, org):
    assert resolve_record(db, org.id, raw("X"), SourcePolicy("no_store", storage_allowed=False)) is None
