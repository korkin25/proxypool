create table stats_shares(
    id int auto_increment,
    foundtime datetime not null,
    user char(34) not null,
    auxuser char(34),
    sharediff float,
    monvalue double not null default 0,
    vtcvalue double not null default 0,
    vtcdiff double not null default 0,
    mondiff double not null default 0,
    vtcpaid bool default 0,
    monpaid bool default 0,
    valid bool,
    primary key (id)
) engine=innodb;

create table stats_transactions(
    id int auto_increment,
    date_sent datetime not null,
    txhash char(64) not null,
    amount double not null,
    coin char(3) not null,
    primary key (id)
) engine=innodb;

create table stats_paidshares(
    id int auto_increment,
    foundtime datetime not null,
    user char(34) not null,
    auxuser char(34),
    sharediff float,
    monvalue double not null default 0,
    vtcvalue double not null default 0,
    vtcdiff double not null default 0,
    mondiff double not null default 0,
    montx_id int,
    vtctx_id int,
    primary key (id),
    foreign key (montx_id) references stats_transactions(id),
    foreign key (vtctx_id) references stats_transactions(id)
) engine=innodb;

create table stats_usertransactions(
    id int auto_increment,
    tx_id int not null,
    user char(34) not null,
    amount double not null,
    coin char(3) not null,
    primary key (id),
    foreign key (tx_id) references stats_transactions(id)
) engine=innodb;
