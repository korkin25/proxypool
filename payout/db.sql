-- MySQL dump 10.13  Distrib 5.5.34, for debian-linux-gnu (i686)
--
-- Host: localhost    Database: tempdb
-- ------------------------------------------------------
-- Server version	5.5.34-0ubuntu0.13.04.1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `stats_paidshares`
--

DROP TABLE IF EXISTS `stats_paidshares`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `stats_paidshares` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `foundtime` datetime NOT NULL,
  `user` char(34) NOT NULL,
  `auxuser` char(34) DEFAULT NULL,
  `plxuser` char(34) DEFAULT NULL,
  `sharediff` float DEFAULT NULL,
  `monvalue` double NOT NULL DEFAULT '0',
  `vtcvalue` double NOT NULL DEFAULT '0',
  `plxvalue` double NOT NULL DEFAULT '0',
  `vtcdiff` double NOT NULL DEFAULT '0',
  `mondiff` double NOT NULL DEFAULT '0',
  `plxdiff` double NOT NULL DEFAULT '0',
  `montx_id` int(11) DEFAULT NULL,
  `plxtx_id` int(11) DEFAULT NULL,
  `vtctx_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `montx_id` (`montx_id`),
  KEY `vtctx_id` (`vtctx_id`),
  KEY `plxtx_id` (`plxtx_id`),
  CONSTRAINT `stats_paidshares_ibfk_1` FOREIGN KEY (`montx_id`) REFERENCES `stats_transactions` (`id`),
  CONSTRAINT `stats_paidshares_ibfk_2` FOREIGN KEY (`vtctx_id`) REFERENCES `stats_transactions` (`id`)
  CONSTRAINT `stats_paidshares_ibfk_3` FOREIGN KEY (`plxtx_id`) REFERENCES `stats_transactions` (`id`)  
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `stats_paidshares`
--

LOCK TABLES `stats_paidshares` WRITE;
/*!40000 ALTER TABLE `stats_paidshares` DISABLE KEYS */;
/*!40000 ALTER TABLE `stats_paidshares` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `stats_shares`
--

DROP TABLE IF EXISTS `stats_shares`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `stats_shares` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `foundtime` datetime NOT NULL,
  `user` char(34) NOT NULL,
  `auxuser` char(34) DEFAULT NULL,
  `plxuser` char(34) DEFAULT NULL,
  `sharediff` float DEFAULT NULL,
  `monvalue` double NOT NULL DEFAULT '0',
  `vtcvalue` double NOT NULL DEFAULT '0',
  `plxvalue` double NOT NULL DEFAULT '0',
  `vtcdiff` double NOT NULL DEFAULT '0',
  `mondiff` double NOT NULL DEFAULT '0',
  `plxdiff` double NOT NULL DEFAULT '0',
  `vtcpaid` tinyint(1) DEFAULT '0',
  `monpaid` tinyint(1) DEFAULT '0',
  `plxpaid` tinyint(1) DEFAULT '0',
  `valid` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `stats_shares`
--

LOCK TABLES `stats_shares` WRITE;
/*!40000 ALTER TABLE `stats_shares` DISABLE KEYS */;
/*!40000 ALTER TABLE `stats_shares` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `stats_transactions`
--

DROP TABLE IF EXISTS `stats_transactions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `stats_transactions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `date_sent` datetime NOT NULL,
  `txhash` char(64) NOT NULL,
  `amount` double NOT NULL,
  `coin` char(3) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `stats_transactions`
--

LOCK TABLES `stats_transactions` WRITE;
/*!40000 ALTER TABLE `stats_transactions` DISABLE KEYS */;
/*!40000 ALTER TABLE `stats_transactions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `stats_usertransactions`
--

DROP TABLE IF EXISTS `stats_usertransactions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `stats_usertransactions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `tx_id` int(11) NOT NULL,
  `user` char(34) NOT NULL,
  `amount` double NOT NULL,
  `coin` char(3) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `tx_id` (`tx_id`),
  CONSTRAINT `stats_usertransactions_ibfk_1` FOREIGN KEY (`tx_id`) REFERENCES `stats_transactions` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `stats_usertransactions`
--

LOCK TABLES `stats_usertransactions` WRITE;
/*!40000 ALTER TABLE `stats_usertransactions` DISABLE KEYS */;
/*!40000 ALTER TABLE `stats_usertransactions` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2014-05-22 19:44:10
